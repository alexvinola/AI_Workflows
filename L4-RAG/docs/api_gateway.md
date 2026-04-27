# API Gateway — Guía de Soporte

## Descripción general

El API Gateway es el punto de entrada único para todos los clientes externos. Se encarga
del enrutamiento, autenticación de API keys, rate limiting y circuit breaking. Corre en
Nginx + Kong sobre Kubernetes, con 3 réplicas en producción.

## Rate limiting

### Configuración actual

- Plan free: 100 peticiones por minuto por API key
- Plan pro: 1000 peticiones por minuto
- Plan enterprise: sin límite (fair use policy)

Cuando un cliente supera el límite recibe un 429 Too Many Requests con el header
`Retry-After` indicando cuántos segundos esperar.

### Clientes que reportan 429 inesperado

Verificar que la API key del cliente corresponde al plan correcto en la tabla `api_keys`.
Si el plan es correcto pero sigue recibiendo 429, puede haber un bug de conteo en el rate
limiter. Escalar al equipo de plataforma con los logs del gateway del período afectado.

## Circuit breaker

El circuit breaker protege los servicios upstream de sobrecarga. Si un servicio falla
más del 50% de las peticiones en 60 segundos, el circuit breaker se abre y el gateway
devuelve 503 Service Unavailable directamente, sin intentar la llamada.

### Estados del circuit breaker

- Closed: funcionamiento normal, todas las peticiones pasan.
- Open: el servicio está caído, el gateway rechaza peticiones con 503.
- Half-open: el gateway deja pasar un 10% de peticiones para probar si el servicio se recuperó.

Para ver el estado actual: `curl http://kong-admin:8001/upstreams/<servicio>/health`

### El circuit breaker no se cierra solo

Si el servicio upstream está sano pero el circuit breaker sigue abierto, reiniciar el
gateway: `kubectl rollout restart deployment/kong`. El estado del circuit breaker es
en memoria — no sobrevive reinicios.

## Logs y diagnóstico

Los logs de acceso del gateway están en CloudWatch bajo el grupo `/prod/api-gateway`.
Cada petición loguea: timestamp, API key (hasheada), endpoint, status code, latencia.

Para filtrar errores 5xx en los últimos 15 minutos:
`aws logs filter-log-events --log-group-name /prod/api-gateway --filter-pattern "5xx"`

## Escalado automático

El gateway escala de 3 a 10 réplicas según CPU. Si hay picos de tráfico sostenidos que
superan las 10 réplicas, el límite se puede aumentar manualmente editando el HPA, pero
requiere aprobación del equipo de infraestructura.
