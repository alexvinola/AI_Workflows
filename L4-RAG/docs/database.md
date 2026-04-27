# Base de Datos PostgreSQL — Guía de Soporte

## Descripción general

La base de datos principal es PostgreSQL 15, desplegada en AWS RDS. Todos los servicios
(auth, pagos, API) comparten la misma instancia con bases de datos separadas por servicio.
El tamaño actual es de 450 GB con backups automáticos diarios a las 03:00 UTC.

## Problemas de rendimiento

### Timeouts de conexión

Si los servicios reportan "connection timeout" o "too many clients":

1. Verificar el número de conexiones activas:
   `SELECT count(*) FROM pg_stat_activity WHERE state = 'active';`
2. El límite es 200 conexiones. Si se supera, identificar qué servicio tiene más conexiones:
   `SELECT application_name, count(*) FROM pg_stat_activity GROUP BY 1 ORDER BY 2 DESC;`
3. Si hay conexiones idle en estado "idle in transaction" durante más de 10 minutos,
   hay un bug de gestión de transacciones en el servicio correspondiente. Matar esas
   conexiones con `SELECT pg_terminate_backend(pid)` y abrir ticket de bug.

### Queries lentas

Las queries que tardan más de 5 segundos se loguean automáticamente. Para ver las más
costosas de las últimas 24 horas:
`SELECT query, calls, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;`

Índices faltantes son la causa más común. Si una query hace sequential scan en una tabla
grande, crear el índice correspondiente.

## Gestión de backups

Los backups automáticos se guardan en S3 durante 30 días. Para restaurar un backup:

1. Crear una nueva instancia RDS desde el snapshot correspondiente.
2. Nunca restaurar sobre la instancia de producción sin aprobación del CTO.
3. El tiempo de restauración estimado es de 45 minutos para la base de datos actual.

## Procedimiento ante pérdida de datos

Si se detecta pérdida o corrupción de datos:
1. Detener inmediatamente el servicio afectado para evitar más escrituras.
2. Escalar a P1 en el sistema de incidencias.
3. El equipo de base de datos tiene acceso a los write-ahead logs (WAL) para recuperación
   point-in-time hasta 7 días atrás.
4. No intentar correcciones manuales en producción sin un DBA presente.

## Escalado

RDS se escala automáticamente en almacenamiento. Para escalar CPU/RAM, se requiere
una ventana de mantenimiento de 30 minutos. Coordinar con el equipo de producto.
