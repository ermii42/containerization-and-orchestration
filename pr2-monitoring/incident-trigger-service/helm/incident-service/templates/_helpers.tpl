{{/*
Разворачивает имя чарта.
*/}}
{{- define "incident-service.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Полное имя (release-name + chart-name), если nameOverride не задан.
*/}}
{{- define "incident-service.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Имя чарта и версия (для label chart).
*/}}
{{- define "incident-service.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Общие labels.
*/}}
{{- define "incident-service.labels" -}}
helm.sh/chart: {{ include "incident-service.chart" . }}
{{ include "incident-service.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels (используются в Deployment.selector и Service.selector).
*/}}
{{- define "incident-service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "incident-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}