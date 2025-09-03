from enum import Enum
from pydantic import BaseModel, Field

from cheshirecat.experimental.form.cat_form import CatForm
from cheshirecat.experimental.form.form_decorator import form


class PizzaBorderEnum(Enum):
    HIGH = "high"
    LOW = "low"


# simple pydantic model
class PizzaOrder(BaseModel):
    pizza_type: str
    pizza_border: PizzaBorderEnum
    phone: str = Field(max_length=10)


@form
class PizzaForm(CatForm):
    description = "Pizza Order"
    model_class = PizzaOrder
    start_examples = ["order a pizza", "I want pizza"]
    stop_examples = [
        "stop pizza order",
        "I do not want a pizza anymore",
    ]

    ask_confirm: bool = True

    def _submit(self, form_data) -> str:
        return f"Form submitted: {form_data}"
