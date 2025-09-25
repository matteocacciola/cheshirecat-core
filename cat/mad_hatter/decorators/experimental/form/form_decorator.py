from .cat_form import CatForm


# form decorator
def form(this_form: CatForm) -> CatForm:
    this_form._autopilot = True
    if this_form.name is None:
        this_form.name = this_form.__name__

    return this_form
