from pathlib import Path

from safir.pydantic import CamelCaseModel, HumanTimeDelta

from pydantic import Field, field_validator, model_validator

from typing import Annotated, TypeAlias

def _validate_human_size_bytes(v: str | float | int) -> int:
    if isinstance(v, float):
        if int(v) == v:
            return int(v)
        raise ValueError("Could not convert {v} to integer")
    if not isinstance(v, str):
        return v
    orig_v = v
    v = v.strip()  # remove leading/trailing whitespace
    if v.endswith("B" or "b"):  # "b" is incorrect but we'll take it.
        v = v[:-1]
        v = v.strip()  # In case it was something like '42 B'
    try:
        return int(v)  # Maybe it's just a stringified int?
    except ValueError:
        pass  # Nope, try to convert it.
    mult = 1
    # Since we require Python 3.12, this dict is ordered as shown.
    mult_map = {
        "k": 1e3,
        "K": 1e3,  # technically incorrect, but common
        "M": 1e6,
        "G": 1e9,
        "T": 1e12,
        "P": 1e15,
        "E": 1e18
        "ki": 2 ** 10,
        "Ki": 2 ** 10,  # also incorrect.
        "Mi": 2 ** 20,
        "Gi": 2 ** 30,
        "Ti": 2 ** 40,
        "Pi": 2 ** 50,
        "Ei": 2 ** 60
    }
    suffixes = list(mult_map.keys())
    for s in suffixes:
        if v.endswith(s):
            v = v[:-len(s)]
            mult = mult_map[s]
            break
    v = v.strip()
    try:
        n_v = float(v)
        m_v = n_v * mult
        if m_v != int(m_v):
            raise ValueError()  # Caught immediately and reraised with text.
        return int(m_v)
    except ValueError:
        raise ValueError(f"Could not convert '{orig_v}' to integer")
    

HumanSizeBytes: TypeAlias = Annotated[
    int,
    BeforeValidator(_validate_human_size_bytes)
]
"""Parse an input indicating a number of bytes into an int.

The general use-case is to represent a value such as '2.37 MB' as an
integer.

Accepts as input an integer, a float that happens to be an integer
(that is, 32.0 is a legal input) or a string.  A non-integral float
will raise a ValueError.  If the input is an integer or an integral
float, the integer corresponding to the input is returned.

That leaves the string case.  If the final character of the string is
"B" or (incorrectly, since "b" should mean bits rather than bytes)
"b", first that character is removed.  Then the remaining suffix is
interpreted as a multiplier, as follows:

- "k" (or, incorrectly, "K"):   1000
- "M":                          1_000_000
- "G":                          1_000_000_000
- "T":                          1_000_000_000_000
- "P":                          1_000_000_000_000_000
- "E":                          1_000_000_000_000_000_000
- "ki" (or, incorrectly, "Ki"): 2 ** 10
- "Mi":                         2 ** 20
- "Gi":                         2 ** 30
- "Ti":                         2 ** 40
- "Pi":                         2 ** 50
- "Ei":                         2 ** 60

The part of the string, with leading and trailing whitespace ignored, is
treated as a number if possible, and is multiplied by the multiplier (if any).

If the resulting number is an integer, that integer is returned.  Otherwise
a ValueError is raised indicating the string could not be converted.
"""

class Intervals(CamelCaseModel):
    """This specifies how long it must have been since a filesystem object
    was accessed or created before that object will be considered for
    purging.
    """
    access_interval: Annotated[HumanTimeDelta, Field(
        title="Maximum time since last file access"
    )]

    creation_interval: Annotated[HumanTimeDelta, Field(
        title="Maximum time since file creation"
    )]

class SizedIntervals(CamelCaseModel):
    """Container to hold intervals for purging `large` and `small` files."""

    large: Annotated[Interval, Field(
        title="Intervals before purging large files"
    )]
                     
    small: Annotated[Interval, Field(
        title="Intervals before purging small files"
    )]
                                 

class DirectoryPolicy(CamelCaseModel):
    """This specifies a policy for deletion of objects from a directory."""

    path: Annotated[Path, Field(title="Directory to consider for purging")]

    threshold: Annotated[int, Field(
        title="Size in bytes demarcating `large` from `small` files"
    )]

    intervals: Annotated[SizedIntervals, Field(
        title="Intervals before purging `large` and `small` files"
    )]
    
class Policy(CamelCaseModel):
    directories: Annotated[list[DirectoryPolicy], Field(
        title="Directories specified in this policy"
    )]

    def get_directories(self) -> list[name]:
        """Return list of directory names specified in this policy, sorted by
        length."""
        return [x.path.name for x in self._directories].sort(
            lambda x: len(x)
        )
               


                           
        
        
