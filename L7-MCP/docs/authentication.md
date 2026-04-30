# Servicio de Autenticación — Guía de Soporte

## Descripción general

El servicio de autenticación gestiona el login de usuarios, la generación de tokens JWT
y la validación de sesiones. Corre en el puerto 8001 y depende de la base de datos
PostgreSQL y de Redis para la caché de sesiones.

## Errores comunes

### 500 Internal Server Error en POST /auth/login

Causas más frecuentes:
- Conexión a la base de datos agotada. El pool de conexiones tiene un máximo de 20. Si
  los logs muestran "connection pool exhausted", hay que aumentar max_connections en la
  configuración o reiniciar el servicio para liberar conexiones colgadas.
- Variable de entorno DATABASE_URL incorrecta tras un deploy. Verificar con:
  `kubectl exec -it <pod> -- env | grep DATABASE_URL`
- Migración de base de datos pendiente. Ejecutar `python manage.py migrate` en el pod.

### 401 Unauthorized — token expirado

Los tokens JWT tienen un TTL de 24 horas. Si los usuarios reportan sesiones caídas de
forma masiva y repentina, verificar que el reloj del servidor no haya tenido un salto
(drift de NTP). Los tokens se validan comparando el campo `exp` con `datetime.utcnow()`.

### 403 Forbidden — permisos insuficientes

El servicio distingue entre autenticación (¿quién eres?) y autorización (¿qué puedes
hacer?). Un 403 significa que el usuario se autenticó correctamente pero no tiene el
rol necesario. Verificar en la tabla `user_roles` de la base de datos.

## Procedimiento de reinicio

1. Verificar que el incidente está registrado en el sistema de tickets.
2. `kubectl rollout restart deployment/auth-service`
3. Monitorizar logs durante 2 minutos: `kubectl logs -f deployment/auth-service`
4. Confirmar que el endpoint `/auth/health` devuelve 200.

## Escalado

Si el reinicio no resuelve el problema o hay más de 1000 usuarios afectados, escalar
inmediatamente al equipo de backend (canal #incidents en Slack) con severidad P1.
Incluir los últimos 100 líneas de logs en el ticket.
