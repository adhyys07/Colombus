"""Cast list; selecting a name browses that person's filmography."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Label, ListItem, ListView

from i18n import _
from models import Movie, Person


class PersonItem(ListItem):
    def __init__(self, person: Person) -> None:
        super().__init__(Label(self._label_text(person)))
        self.person = person

    @staticmethod
    def _label_text(person: Person) -> Text:
        line = Text(person.name, style="bold")
        if person.role:
            line.append(f"  {person.role}", style="dim")
        return line


class CastPane(ListView):
    BORDER_TITLE = _("cast")

    async def show_movie(self, movie: Movie) -> None:
        await self.clear()
        for person in movie.cast:
            await self.append(PersonItem(person))

    @property
    def selected_person(self) -> Person | None:
        return getattr(self.highlighted_child, "person", None)
