from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CalendarEvent:
    id: str
    source: str           # "outlook_calendar", "google_calendar", "teams", "jira", "clickup"
    title: str
    start: datetime
    end: datetime
    all_day: bool = False
    location: str = ""
    description: str = ""
    url: str = ""
    attendees: list = field(default_factory=list)  # [{"name": str, "email": str}]
    color: str = "#748cab"
    organizer: str = ""

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "source":      self.source,
            "title":       self.title,
            "start":       self.start.replace(tzinfo=None).isoformat(),
            "end":         self.end.replace(tzinfo=None).isoformat(),
            "all_day":     self.all_day,
            "location":    self.location,
            "description": self.description,
            "url":         self.url,
            "attendees":   self.attendees,
            "color":       self.color,
            "organizer":   self.organizer,
        }
