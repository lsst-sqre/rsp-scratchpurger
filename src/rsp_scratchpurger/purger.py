"""The Purger class reads its policy document and provides mechanisms for
planning actions, reporting its plans, and executing its plans.
"""

import yaml

from pathlib import Path

from .constants import POLICY_FILE

class Purger:

    def __init__(
        self,
        policy_file: Path = POLICY_FILE,
        dry_run:bool = False,
        debug: bool = False
    ) -> None:
        self._plan:
                 
