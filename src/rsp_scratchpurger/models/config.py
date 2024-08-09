from pathlib import Path

from safir.pydantic import CamelCaseModel

from pydantic import Field

from typing import Annotated

class Config(CamelCaseModel):

    policy_file: Annotated[Path, Field(title="Policy file location")]

    dry_run: Annotated[bool, Field(title="Report rather than execute plan",
                                   default=False)]

    debug: Annotated[bool, Field(title="Verbose debugging output",
                                 default=False)]
    
