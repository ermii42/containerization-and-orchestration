import os
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

logger = logging.getLogger(__name__)

def setup_tracing(app=None):
    service_name = os.getenv("OTEL_SERVICE_NAME", "incident-trigger-service")
    jaeger_endpoint = os.getenv("JAEGER_ENDPOINT", "")

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if jaeger_endpoint:
        exporter = OTLPSpanExporter(endpoint=jaeger_endpoint, insecure=True)
        logger.info(f"Tracing -> Jaeger at {jaeger_endpoint}")
    else:
        exporter = ConsoleSpanExporter()
        logger.info("Tracing -> console (no JAEGER_ENDPOINT set)")

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    HTTPXClientInstrumentor().instrument()
    if app:
        FastAPIInstrumentor.instrument_app(app)

    return provider