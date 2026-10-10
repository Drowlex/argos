from dagster import op
from app.services import test_service
from app.core.settings import get_settings
settings = get_settings()


@op
def valor(context):
    return 5

@op
def suma_1(context, valor):
    return valor + 1

@op
def resta_1(context, valor):
    return valor - 1

@op
def print_resultado(context, result):
    context.log.info(f"Resultado {result}")

@op
def hello_world(context):
    context.log.info(f"Hello World {settings.APP_NAME}")

@op
def greetings(context):
    context.log.info(f"Hello {context.op_config['name']} {context.op_config['lastname']}")

@op
def suma(context):
    return test_service.suma(context.op_config['a'], context.op_config['b'])

@op
def print_total(context, result: int):
    context.log.info(f"El resultado es: {result}")
