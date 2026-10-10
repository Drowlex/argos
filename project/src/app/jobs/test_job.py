from dagster import job
from app import operations

@job()
def test_operacion():
    valor = operations.valor()
    result_suma = operations.suma_1(valor)
    operations.print_resultado(result_suma)
    result_rest = operations.resta_1(valor)
    operations.print_resultado(result_rest)

@job()
def test_hello():
    operations.hello_world()

@job(
    config = {
        "ops": {
            "greetings": {
                "config": {
                    "name": 'Pepe',
                    "lastname": 'Grillo'
                }
            }
        }
    }
)
def test_greetings():
    operations.greetings()

@job(
    config = {
        "ops": {
            "suma": {
                "config": {
                    "a": 10,
                    "b": 5
                }
            }
        }
    }
)
def test_calculator():
    result = operations.suma()
    operations.print_total(result)