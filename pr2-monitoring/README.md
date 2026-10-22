# Лаба 2 — Мониторинг сервиса: метрики, логи, трейсы


## Часть 0 — Свой сервис

Сгенерируем HTTP-сервис `api` с эндпоинтами, чтобы самому провоцировать ситуации:

- `GET /health` — возвращает `ok`;
- `GET /fail` — возвращает ошибку 5xx и увеличивает счётчик ошибок;
- `GET /slow` — отвечает медленно (спит 1–3 секунды);
- `GET /load` — делает пачку запросов к себе, чтобы подскочил RPS.

Работаем только в Kubernetes: поднимем локальный кластер minikube и развернем весь стек разворачивай через Helm.

```
minikube start --driver=kvm --cpus=5 --memory=12288 --disk-size=10g
kubectl create namespace tracing
helm repo add jaegertracing https://jaegertracing.github.io/helm-charts
helm repo update

helm repo add jetstack https://charts.jetstack.io
helm repo update

# Устанавливаем cert-manager с CRD в отдельный namespace
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set installCRDs=true

helm install jaeger jaegertracing/jaeger-operator -n tracing \
  --create-namespace \
  --set rbac.clusterRole=true \
  --set jaeger.create=false

kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=jaeger-operator -n tracing --timeout=60s

helm upgrade jaeger jaegertracing/jaeger-operator -n tracing \
  --set jaeger.create=true \
  --set jaeger.spec.storage.type=memory

kubectl create namespace incident

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false

helm install incident-service ./incident-trigger-service/helm/incident-service \
  -n incident \
  --set otel.jaegerEndpoint="http://jaeger-jaeger-operator-jaeger-collector.tracing.svc.cluster.local:4317"
```
```
# Поды
kubectl get pods -n incident

# Проброс порта для теста
kubectl port-forward -n incident svc/incident-service 8000:8000 &
```
![alt text](src/image.png)

```
kubectl port-forward -n tracing svc/jaeger-jaeger-operator-jaeger-query 16686:16686 --address 0.0.0.0
```

## Часть 1 — Метрики (Prometheus + Grafana)

**Поднимем Prometheus**

Установка kube-prometheus-stack
```
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install monitoring prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace
```
![alt text](src/image-1.png)

```
kubectl port-forward -n monitoring svc/monitoring-grafana 3001:80 --address 0.0.0.0
```
Для получения сгенерированного админ-пароля
```
kubectl get secret --namespace monitoring monitoring-grafana -o jsonpath="{.data.admin-password}" | base64 --decode ; echo
```

**Настройка scrape /metrics сервиса**
сервис отдаёт метрики на /metrics порта 8000. Чтобы Prometheus их собирал, нужен ServiceMonitor — это CRD от Prometheus Operator.
Создайте файл servicemonitor.yaml:

Применяем
```
kubectl apply -f ./incident-trigger-service/helm/incident-service/templates/servicemonitor.yaml
```
Проверка, что Prometheus видит таргет: откройте Prometheus UI:

```
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9091:9090 --address 0.0.0.0
```
![alt text](src/image-2.png)

**Дашборд RED**

**Панель 1 — Rate (RPS)**
```
sum(rate(http_requests_total{job="incident-service"}[1m]))
```
http_requests_total — Counter из app/metrics.py.

**Панель 2 — Errors (доля ошибок в %)**
```
100 * sum(rate(http_requests_total{job="incident-service", status_code=~"5.."}[1m]))
    / sum(rate(http_requests_total{job="incident-service"}[1m]))
```

**Панель 3 — Duration (p95 latency)**
```
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket{job="incident-service"}[5m])) by (le)
)
```
Результат настройки дашборда:
![alt text](src/image-3.png)

## Часть 2 — Логи (Loki + Grafana)

Добавим репозиторий Grafana
```
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Ставим Loki в неймспейс monitoring
helm install loki grafana/loki -n monitoring -f ./incident-trigger-service/helm/incident-service/loki-values.yaml
```
Установка Grafana Alloy (агент сбора логов)
```
helm install alloy grafana/alloy -n monitoring \
  --set controller.type=daemonset \
  --set alloy.configMap.create=true
```
Настройка Alloy для сбора логов сервиса
Создайте файл alloy-config.alloy со следующим содержимым:

Примените конфиг:
```
kubectl create configmap alloy-config \
  --from-file=config.alloy=./incident-trigger-service/alloy-config.alloy \
  -n monitoring
```
Теперь нужно, чтобы Alloy использовал этот ConfigMap. Обновите релиз Alloy:
```
helm upgrade alloy grafana/alloy -n monitoring \
  --set controller.type=daemonset \
  --set alloy.configMap.create=false \
  --set alloy.configMap.name=alloy-config \
  --set alloy.configMap.key=config.alloy
```
Подключение Loki к Grafana
Loki нужно добавить как data source в Grafana, чтобы искать логи через UI.
```
kubectl port-forward -n monitoring svc/loki 3100:3100
```
![alt text](src/image-4.png)

 Проверка: дёргаем /fail и ищем в логах
```
curl -v http://localhost:8000/fail
```
 ![alt text](src/image-5.png)

## Часть 3 — Трейсы (OpenTelemetry + Jaeger)

Трейс — это путь одного запроса через сервис (а в больших системах — через всю цепочку сервисов), собранный из отрезков-спанов. У каждого спана есть имя, начало, конец и длительность, а вложенные спаны показывают, из чего сложилось общее время. Трейсинг отвечает на вопрос «на каком шаге ушло время», когда по метрикам видно «где-то медленно», а где именно — непонятно..

Поднимем Jaeger:
```
kubectl set env deployment/incident-service -n incident \
  JAEGER_ENDPOINT="http://jaeger-jaeger-operator-jaeger-collector.tracing.svc.cluster.local:4317"
```
```
kubectl port-forward -n tracing svc/jaeger-jaeger-operator-jaeger-query 16686:16686
```
![alt text](src/image-6.png)

Направим на него OTLP-экспортёр сервиса.  трейс `/fail` — с красным ошибочным спаном
```
curl http://localhost:8000/fail

```
Возьмем `trace_id` из лога в Grafana и найди по нему тот же трейс в Jaeger.
![alt text](src/image-7.png)
![alt text](src/image-8.png)
## Часть 4 — Алерты (Alertmanager + Karma)

Придумем 3 алерта и опишем их в PrometheusRule.yaml: 

**Алерт 1. Доля ошибок 5xx выше 5% несколько минут подряд**
Что ловит: устойчивый рост доли серверных ошибок. Пользователи прямо сейчас получают 500-е.

Почему критично: это прямая деградация пользовательского опыта. Даже если RPS небольшой, 10% ошибок означает, что каждый десятый запрос ломается. Кратковременный всплеск (одна-две секунды) можно игнорировать, но если ошибки держатся 5 минут — это уже инцидент.

**Алерт 2. p95 времени ответа выше 2 секунд**
Что ловит: замедление сервиса, из-за которого пользователи ждут слишком долго. Не «немного медленнее», а именно неприемлемо долго.

Почему критично: latency — это то, что пользователь чувствует напрямую. p95 = 2 сек означает, что каждый двадцатый запрос идёт дольше двух секунд. Для интерактивного сервиса это плохо. Если ещё растёт, скоро упрётесь в таймауты клиентов и вышестоящих прокси.

**Алерт 3. Сервис не отвечает вовсе (метрики пропали)**
Что ловит: сервис полностью недоступен. Prometheus не может снять метрики с таргета.

Почему критично: это самый тяжёлый тип инцидента. Пользователи вообще ничего не получают. При этом дашборды могут быть пустыми — потому что данных просто нет. Нужен отдельный алерт именно на «отсутствие данных», а не на «плохие данные».

Применим PrometheusRule.yaml к prometheus
```
kubectl apply -f PrometheusRule.yaml
```
Проверим, что prometheus подхватил правила
```
kubectl get prometheusrules -n monitoring
```

**Поверх Alertmanager поднимем Karma** 

— веб-дашборд, который показывает все активные алерты в одном окне, с группировкой и фильтрами. Штатный интерфейс Alertmanager для этого бедноват, а Karma удобна, когда алертов становится много и за ними надо наблюдать вживую.

Установка через Helm
```
helm repo add wiremind https://wiremind.github.io/wiremind-helm-charts
helm repo update
```
Уточняем имя сервиса Alertmanager
```
kubectl get svc -n monitoring | grep alertmanager
```
![alt text](src/image-9.png)
```
helm install karma wiremind/karma -n monitoring \
  --set config.alertmanager.servers[0].name=monitoring \
  --set config.alertmanager.servers[0].uri=http://monitoring-kube-prometheus-alertmanager.monitoring.svc.cluster.local:9093
```

Проверка
```
kubectl get pods -n monitoring -l app.kubernetes.io/name=karma
kubectl port-forward -n monitoring svc/karma 8081:80 --address 0.0.0.0
```

**Провоцируем HighErrorRate**
```
# Порт-форвард на сервис
kubectl port-forward -n incident svc/incident-service 8000:8000 --address 0.0.0.0

# Дёргаем /fail в цикле — чтобы доля ошибок превысила 5%
curl -X GET "http://localhost:8000/load?target=/fail&total=1000&concurrent=50"
```
![alt text](src/image-10.png)

**Провоцируем HighLatencyP95**
```
curl -X GET "http://localhost:8000/load?target=/slow&total=300&concurrent=20"
```
![alt text](src/image-12.png)

**Провоцируем ServiceDown**
```
kubectl scale deployment incident-service --replicas=0 -n incident
```
![alt text](src/image-11.png)