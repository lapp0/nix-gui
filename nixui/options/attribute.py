from dataclasses import dataclass, field
import functools
import re
from typing import List
import csv


@dataclass(frozen=True)
class Attribute:
    loc: List[str] = field(default_factory=list)

    def __init__(self, path):
        if isinstance(path, list):
            object.__setattr__(self, 'loc', path)
        elif isinstance(path, str):
            object.__setattr__(self, 'loc', next(csv.reader([path], delimiter='.', quotechar='"')))
        else:
            raise TypeError(str(type(path)), path)

    @classmethod
    def from_insertion(cls, attribute_set, attribute):
        return cls(attribute_set.loc + [attribute])

    def get_set(self):
        return Attribute(self.loc[:-1])

    def get_end(self):
        return self.loc[-1]

    def startswith(self, attribute_set):
        if len(attribute_set) > len(self):
            return False
        for i, key in enumerate(attribute_set):
            if self[i] != key:
                return False
        return True

    def is_list_index(self, key_idx=-1):
        """
        Determines whether the key at index idx is a list index.
        For example, in foo.bar."[5]".baz, the 2nd key, "[5]" is a list index
        whereas the 0th, 1st, and 3rd key aren't.
        """
        return self.get_attr_key_list_index(self[key_idx]) is not None

    @staticmethod
    def get_attr_key_list_index(key_str):
        """
        Given a key in an attribute path, return its integer list index value if it is a list index
        "[22]" -> 22
        "foo" -> None
        """
        # TODO: fix https://github.com/nix-gui/nix-gui/issues/218
        if key_str.startswith('[') and key_str.endswith(']'):
            try:
                return int(key_str[1:-1])
            except ValueError:
                return None
        return None

    def __bool__(self):
        return bool(self.loc)

    def __getitem__(self, subscript):
        if isinstance(subscript, slice):
            return Attribute(self.loc[subscript])
        else:
            return self.loc[subscript]

    def __iter__(self):
        return iter(self.loc)

    def __len__(self):
        return len(self.loc)

    def __lt__(self, other):
        # defined such that iterating over sorted attributes is a bredth first search
        return (-len(self), str(self)) < (-len(other), str(other))

    def __str__(self):
        return '.'.join([
            attribute
            if attribute_key_neednt_be_quoted(attribute)
            else f'"{attribute}"'
            for attribute in self.loc
        ])

    def __repr__(self):
        return f"Attribute('{str(self)}')"

    def __hash__(self):
        return hash(tuple(self.loc))


"""
regexp based on
https://github.com/NixOS/nix/blob/99f8fc995b2f080cc0a6fe934c8d9c777edc3751/src/libexpr/lexer.l#L97
https://github.com/NixOS/nixpkgs/blob/8da27ef161e8bd0403c8f9ae030ef1e91cb6c475/pkgs/tools/nix/nixos-option/libnix-copy-paste.cc#L52

determines whether an attribute path key should be quoted
"""
NIX_PATH_KEY_REGEXP = re.compile(r'^[a-zA-Z\_][a-zA-Z0-9\_\'\-]*$')


def attribute_key_neednt_be_quoted(attribute_str):
    return bool(NIX_PATH_KEY_REGEXP.search(attribute_str))
