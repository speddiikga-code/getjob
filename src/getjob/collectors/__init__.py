"""One collector per job site, keyed like `sources:` in config/search.yaml."""

from getjob.collectors.alio import AlioCollector
from getjob.collectors.base import Collector
from getjob.collectors.incruit import IncruitCollector
from getjob.collectors.jobkorea import JobKoreaCollector
from getjob.collectors.jumpit import JumpitCollector
from getjob.collectors.linkedin import LinkedInCollector
from getjob.collectors.peoplenjob import PeopleNJobCollector
from getjob.collectors.remember import RememberCollector
from getjob.collectors.saramin import SaraminCollector
from getjob.collectors.wanted import WantedCollector
from getjob.collectors.work24 import Work24Collector
from getjob.settings import Settings
from getjob.web import Http

COLLECTORS: dict[str, type[Collector]] = {
    c.key: c
    for c in [
        LinkedInCollector,
        JobKoreaCollector,
        SaraminCollector,
        WantedCollector,
        IncruitCollector,
        Work24Collector,
        RememberCollector,
        JumpitCollector,
        PeopleNJobCollector,
        AlioCollector,
    ]
}


def build_collector(key: str, http: Http, settings: Settings) -> Collector:
    if key == SaraminCollector.key:
        key_value = settings.saramin_api_key
        return SaraminCollector(http, key_value.get_secret_value() if key_value else None)
    return COLLECTORS[key](http)
