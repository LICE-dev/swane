from enum import Enum
from swane.config.PrefCategory import PrefCategory


class GlobalPrefCategoryList(Enum):
    MAIN = PrefCategory("main", "Global settings")
    PERFORMANCE = PrefCategory("performance", 'Performance')
    OPTIONAL_SERIES = PrefCategory("optional_series", 'Optional series')

    def __str__(self):
        return self.value.name
