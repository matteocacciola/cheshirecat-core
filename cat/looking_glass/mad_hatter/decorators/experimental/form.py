import json
from abc import ABC, abstractmethod
from typing import List, Dict, Type
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ValidationError
from slugify import slugify

from cat.log import log
from cat.looking_glass.mad_hatter.procedures import CatProcedure, CatProcedureType
from cat.looking_glass.models import AgentOutput
from cat.services.factory.agentic_workflow import AgenticTask, CoreAgenticWorkflow
from cat.utils import Enum, parse_json


# Conversational Form State
class CatFormState(Enum):
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"
    WAIT_CONFIRM = "wait_confirm"
    CLOSED = "closed"


class CatForm(CatProcedure, ABC):  # base model of forms
    model_class: Type[BaseModel]
    stop_examples: List[str] = []
    ask_confirm: bool = False
    _autopilot = False

    def __init__(self):
        if not hasattr(self, "name") or not self.name:
            self.name = type(self).__name__
        self.name = slugify(self.name.strip(), separator="_")

        self._state = CatFormState.INCOMPLETE
        self._model: Dict = {}

        self._errors: List[str] = []
        self._missing_fields: List[str] = []

        self._agent = CoreAgenticWorkflow()

    @property
    def cat(self):
        """
        Returns:
            StrayCat: StrayCat instance
        """
        return self.stray

    @property
    def state(self) -> CatFormState:
        return self._state

    @property
    def autopilot(self) -> bool:
        return self._autopilot

    def dictify_input_params(self) -> Dict:
        return {}

    @classmethod
    def reconstruct_from_params(cls, input_params: Dict) -> "CatForm":
        # CatForm has no constructor params
        return cls()

    def langchainfy(self) -> List[StructuredTool]:
        """
        Convert CatProcedure to a langchain compatible StructuredTool object.

        Returns:
            The langchain compatible StructuredTool object.
        """
        description = self.description + ("\n\nE.g.:\n" if self.examples else "")
        for example in self.examples:
            description += f"- {example}\n"

        return [StructuredTool.from_function(
            name=self.name,
            description=description,
            func=self.next,
        )]

    @property
    def type(self) -> CatProcedureType:
        return CatProcedureType.TOOL

    @abstractmethod
    def submit(self, form_data) -> str:
        pass

    # Check user confirm the form data
    async def _confirm(self) -> bool:
        # Get user message
        user_message = self.stray.cheshire_cat.working_memory.user_message.text

        # Confirm prompt
        confirm_prompt = """Your task is to produce a JSON representing whether a user is confirming or not.
JSON must be in this format:
```json
{{
    "confirm": // type boolean, must be `true` or `false` 
}}
```"""

        # Queries the LLM and check if user agrees or not
        response = await self._run_agent(prompt_template=confirm_prompt, prompt_variables={"input": user_message})
        return "true" in response.output.lower()

    # Check if the user wants to exit the form
    # it is triggered at the beginning of every form.next()
    async def _check_exit_intent(self) -> bool:
        # Get user message
        user_message = self.stray.cheshire_cat.working_memory.user_message.text

        # Stop examples
        stop_examples = """
Examples where {"exit": true}:
- exit form
- stop it"""

        stop_examples += "".join([f"\n- {se}" for se in self.stop_examples])

        # Check exit prompt
        check_exit_prompt = f"""Your task is to produce a JSON representing whether a user wants to exit or not.
JSON must be in this format:
```json
{{
    "exit": // type boolean, must be `true` or `false`
}}
```

{stop_examples}

JSON:
"""

        # Queries the LLM and check if user agrees or not
        response = await self._run_agent(prompt_template=check_exit_prompt, prompt_variables={"input": user_message})
        return "true" in response.output.lower()

    # Updates the form with the information extracted from the user's response
    # (Return True if the model is updated)
    async def _update(self):
        # Conversation to JSON
        json_details = await self._extract()
        json_details = self._sanitize(json_details)

        # model merge old and new
        self._model = self._model | json_details

        # Validate new_details
        self._validate()

    def _message(self) -> str:
        if self._state == CatFormState.CLOSED:
            return f"Form {type(self).__name__} closed"

        if self._state == CatFormState.WAIT_CONFIRM:
            output = self._generate_base_message()
            output += "\n --> Confirm? Yes or no?"
            return output

        if self._state == CatFormState.INCOMPLETE:
            return self._generate_base_message()

        return "Invalid state"

    def _generate_base_message(self):
        separator = "\n - "
        missing_fields = ""
        if self._missing_fields:
            missing_fields = "\nMissing fields:"
            missing_fields += separator + separator.join(self._missing_fields)
        invalid_fields = ""
        if self._errors:
            invalid_fields = "\nInvalid fields:"
            invalid_fields += separator + separator.join(self._errors)

        out = f"""Info until now:

```json
{json.dumps(self._model, indent=4)}
```
{missing_fields}
{invalid_fields}
"""
        return out

    # Extract model information from user message
    async def _extract(self):
        json_str = await self._run_agent(prompt_template=self._extraction_prompt())

        # json parser
        try:
            output_model = parse_json(json_str.output)
        except Exception as e:
            output_model = {}
            log.warning("LLM did not produce a valid JSON")
            log.warning(e)

        return output_model

    def _extraction_prompt(self, latest_n: int = 10):
        history = "".join([str(h) for h in self.stray.cheshire_cat.working_memory.history[-latest_n:]])

        # JSON structure
        # BaseModel.__fields__['my_field'].type_
        json_structure = "{"
        json_structure += "".join([
            f'\n\t"{field_name}": // {field.description if field.description else ""} Must be of type `{field.annotation.__name__}` or `null`'
            for field_name, field in self.model_class().model_fields.items()
        ])  # field.required?
        json_structure += "\n}"

        # TODO: reintroduce examples
        prompt = f"""Your task is to fill up a JSON out of a conversation.
The JSON must have this format:
```json
{json_structure}
```

This is the current JSON:
```json
{json.dumps(self._model, indent=4)}
```

This is the conversation:
{history}

Updated JSON:
"""

        # TODO: convo example (optional but supported)

        prompt_escaped = prompt.replace("{", "{{").replace("}", "}}")
        return prompt_escaped

    # Sanitize model (take away unwanted keys and null values)
    # NOTE: unwanted keys are automatically taken away by pydantic
    def _sanitize(self, model):
        # preserve only non-null fields
        null_fields = [None, "", "None", "null", "lower-case", "unknown", "missing"]
        model = {key: value for key, value in model.items() if value not in null_fields}

        return model

    # Validate model
    def _validate(self):
        self._missing_fields = []
        self._errors = []

        try:
            # Attempts to create the model object to update the default values and validate it
            self.model_class(**self._model).model_dump(mode="json")

            # If model is valid change state to COMPLETE
            self._state = CatFormState.COMPLETE
        except ValidationError as e:
            # Collect ask_for and errors messages
            for error_message in e.errors():
                field_name = error_message["loc"][0]
                if error_message["type"] == "missing":
                    self._missing_fields.append(field_name)
                else:
                    self._errors.append(f'{field_name}: {error_message["msg"]}')
                    del self._model[field_name]

            # Set state to INCOMPLETE
            self._state = CatFormState.INCOMPLETE

    async def next(self) -> str:
        if self.state == CatFormState.CLOSED:
            # form is closed
            return ""

        # continue form
        try:
            should_exit = await self._check_exit_intent()

            # If state is WAIT_CONFIRM, check user confirm response.
            if self._state == CatFormState.WAIT_CONFIRM:
                should_confirm = await self._confirm()
                if should_confirm:
                    result = self.submit(self._model)
                    self._state = CatFormState.CLOSED
                    return result

                self._state = CatFormState.CLOSED if should_exit else CatFormState.INCOMPLETE
            elif should_exit:
                self._state = CatFormState.CLOSED

            # If the state is INCOMPLETE, execute model update
            # (and change state based on validation result)
            if self._state == CatFormState.INCOMPLETE:
                await self._update()

            # If state is COMPLETE, ask confirm (or execute action directly)
            if self._state == CatFormState.COMPLETE:
                if not self.ask_confirm:
                    result = self.submit(self._model)
                    self._state = CatFormState.CLOSED
                    return result

                self._state = CatFormState.WAIT_CONFIRM

            # if state is still INCOMPLETE, recap and ask for new info
            return self._message()
        except Exception as e:
            log.error(f"Error while executing form: {e}")
            return ""

    async def _run_agent(self, prompt_template: str, prompt_variables: Dict | None = None) -> AgentOutput:
        response = await self._agent.run(
            task=AgenticTask(
                prompt=ChatPromptTemplate.from_messages([
                    HumanMessagePromptTemplate.from_template(template=prompt_template)
                ]),
                prompt_variables=prompt_variables,
            ),
            llm=self.stray.large_language_model,
        )
        return response

# form decorator
def form(this_form: CatForm) -> CatForm:
    this_form._autopilot = True
    if this_form.name is None:
        this_form.name = this_form.__name__

    return this_form
