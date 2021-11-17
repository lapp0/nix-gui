"""
based on https://github.com/NixOS/nixpkgs/blob/master/lib/types.nix
"""
import abc
import dataclasses
import typing


def from_nix_type_str(nix_type_str, or_legal=True):
    """
    TODO: eval nested types, e.g.
    nix-instantiate --eval '<nixpkgs/nixos>' --arg configuration '{}' \
    -A "options.services.zrepl.settings.type.nestedTypes.freeformType.nestedTypes.elemType.nestedTypes.right.nestedTypes.elemType.nestedTypes.elemType.nestedTypes.left"
    we also need to extract validation data, e.g. "not containing newlines or colons"
      - does nix include a regexp or expression for us to validate with?
    """
    # cases where there is no criteria to recurse on
    if nix_type_str == '':
        return None

    # return types for Function()
    elif nix_type_str == 'listOf':
        return ListOfType()
    elif nix_type_str.startswith('list of') and nix_type_str.endswith('s'):
        return ListOfType(
            from_nix_type_str(nix_type_str.removeprefix('list of ').removesuffix('s'))
        )
    elif nix_type_str.startswith('attribute set of') and nix_type_str.endswith('s'):
        return AttrsOfType(
            from_nix_type_str(nix_type_str.removeprefix('attribute set of ').removesuffix('s'))
        )

    # or type: this can be ambiguous, for example "list of int or bools or package"
    # for each " or ", we split and recurse:
    # - (list of int) or (bools or package) - illegal because no "s" at end of "list of ints"
    # - (list of int or bools) or (package) - legal
    # then we reconstruct the result `Either(Either(a, b), c)` into `Either(a, b, c)`
    # additionally, if the or has two choices, and the second choice ends with "convertible to it", it is a CoercedToType
    elif ' or ' in nix_type_str and or_legal:
        chunks = nix_type_str.split(' or ')
        for i in range(1, len(chunks)):
            try:
                left = from_nix_type_str(' or '.join(chunks[:i]))
                right_text = ' or '.join(chunks[i:])
                if right_text.endswith(' convertible to it'):
                    right = from_nix_type_str(right_text.removesuffix(' convertible to it'))
                    is_coerced = True
                else:
                    right = from_nix_type_str(right_text)
                    is_coerced = False
            except ValueError:
                continue

            if is_coerced:
                return CoercedToType(final_type=left, coerced_type=right)
            elif isinstance(left, EitherType):
                if isinstance(right, EitherType):
                    return EitherType(list(left.subtypes) + list(right.subtypes))
                else:
                    return EitherType(list(left.subtypes) + [right])
            elif isinstance(right, EitherType):
                return EitherType([left] + list(right.subtypes))
            else:
                return EitherType([left, right])
        else:
            return from_nix_type_str(nix_type_str, or_legal=False)

    # types "containing" other types in their definitions
    elif nix_type_str.startswith('list of') and nix_type_str.endswith('s'):
        return ListOfType(
            from_nix_type_str(nix_type_str.removeprefix('list of ').removesuffix('s'))
        )
    elif nix_type_str.startswith('attribute set of'):
        return AttrsOfType(
            from_nix_type_str(nix_type_str.removeprefix('attribute set of ').removesuffix('s'))
        )
    elif nix_type_str.startswith('function that evaluates to a(n) '):
        return FunctionType(
            from_nix_type_str(nix_type_str.removeprefix('function that evaluates to a(n) '))
        )

    # simple types with criteria
    elif nix_type_str.startswith('lazy attribute set of'):
        try:
            return AttrsOfType(
                from_nix_type_str(nix_type_str.removeprefix('lazy attribute set of ')),
                lazy=True
            )
        except:
            return AttrsOfType(
                from_nix_type_str(
                    nix_type_str.removeprefix('lazy attribute set of ').removesuffix('s')
                ),
                lazy=True
            )
    elif nix_type_str.startswith('non-empty list of') and nix_type_str.endswith('s'):
        return ListOfType(
            from_nix_type_str(nix_type_str.removeprefix('non-empty list of ').removesuffix('s')),
            minimum=1,
        )
    elif nix_type_str.startswith('pair of'):
        return ListOfType(
            from_nix_type_str(nix_type_str.removeprefix('pair of ')),
            minimum=2,
            maximum=2,
        )
    elif nix_type_str.startswith('string concatenated with') or nix_type_str.startswith('strings concatenated with'):
        # TODO: fix this hack, (((list of) strings) concatenated with "foo"), not # ((list of) string concatenated with "foo"s)
        s = nix_type_str.split('concatenated with')[1]
        s = s.strip('"')
        return StrType(concatenated_with=s)
    elif nix_type_str.startswith('string (with check: '):
        check = nix_type_str.split('(with check: ')[1].removesuffix(')')
        return StrType(check=check)
    elif nix_type_str.startswith('string matching the pattern'):
        return StrType(
            legal_pattern=nix_type_str.removeprefix('string matching the pattern ')
        )
    elif nix_type_str.startswith('string without spaces'):
        return StrType(legal_pattern=r'\S*')
    elif nix_type_str in ('string, not containing newlines or colons'):
        return StrType(legal_pattern=r'[^\r\n:]*')
    elif nix_type_str == 'unsigned integer, meaning >=0':
        return IntType(minimum=0)
    elif nix_type_str == 'positive integer, meaning >0':
        return IntType(minimum=1)
    elif nix_type_str == '16 bit unsigned integer; between 0 and 65535 (both inclusive)':
        return IntType(minimum=0, maximum=65535)
    elif nix_type_str == '8 bit unsigned integer; between 0 and 255 (both inclusive)':
        return IntType(minimum=0, maximum=255)
    elif nix_type_str.startswith('integer between') and nix_type_str.endswith('(both inclusive)'):
        s = nix_type_str.removeprefix('integer between ').removesuffix(' (both inclusive)')
        minimum, maximum = s.split(' and ')
        return IntType(minimum=int(minimum), maximum=int(maximum))
    elif nix_type_str.startswith('one of'):
        s = nix_type_str.removeprefix('one of ')
        return OneOfType([x.strip('"') for x in s.split(', ')])
    elif nix_type_str in ('path, not containing newlines', 'path, not containing newlines or colons'):
        return PathType()  # TODO: special handling
    elif nix_type_str.startswith('a floating point number in range'):
        s = nix_type_str.removeprefix('a floating point number in range ').lstrip('[').rstrip(']')
        minimum, maximum = s.split(', ')
        return FloatType(minimum=float(minimum), maximum=float(maximum))  # TODO: special handling

    # simple types
    elif nix_type_str == 'lambda':
        return FunctionType()
    elif nix_type_str == 'attribute set':
        return AttrsType()
    elif nix_type_str == 'boolean':
        return BoolType()
    elif nix_type_str == 'unspecified':
        return UnspecifiedType()
    elif nix_type_str == 'string':
        return StrType()
    elif nix_type_str in ('int', 'signed integer', 'integer of at least 16 bits'):
        return IntType()
    elif nix_type_str in ('float', 'floating point number'):
        return FloatType()
    elif nix_type_str == 'path':
        return PathType()
    elif nix_type_str == 'package':
        return PackageType()
    elif nix_type_str == 'submodule':
        return SubmoduleType()
    elif nix_type_str == 'null':
        return NullType()
    elif nix_type_str == 'anything':
        return AnythingType()

    # no good handling yet
    elif (
        nix_type_str.startswith('ncdns.conf configuration type') or
        nix_type_str.startswith('libconfig configuration') or
        nix_type_str.startswith('privoxy configuration type') or
        nix_type_str.startswith('unbound.conf configuration type.') or
        nix_type_str in (
            'systemd option',
            'JSON value',
            'Json value',
            'YAML value',
            'Yaml value',
            'TOML value',
            'session name',
            'settings option',
            'template name',
            'printable string without spaces, # and /',
            'string of the form number{b|k|M|G}',
            'Go duration (https://golang.org/pkg/time/#ParseDuration)',
            'sysctl option value',
            'Toplevel NixOS config',
            'INI atom (null, bool, int, float or string)',
            'nixpkgs config',
            'nixpkgs overlay',
            'An evaluation of Nixpkgs; the top level attribute set of packages',
            'davmail config type (str, int, bool or attribute set thereof)',
            'freeciv-server params',
            'limesurvey config type (str, int, bool or attribute set thereof)',
            'Minecraft UUID',
            'LDAP value',
            'tmpfiles.d(5) age format',
            'INI atom (null, bool, int, float or string) or a non-empty list of them',
            'dataset/template options',
            'tuple of (unsigned integer, meaning >=0 or one of "level auto", "level full-speed", "level disengage") (unsigned integer, meaning >=0) (unsigned integer, meaning >=0)',
            'Traffic Server records value',
            'package with provided sessions',
            'znc values (null, atoms (str, int, bool), list of atoms, or attrsets of znc values)',
            'string containing all of the characters %Y, %m, %d, %H, %M, %S',
            'Concatenated string',
        )
        ):
        return AnythingType()

    else:
        raise ValueError(nix_type_str)


def type_of_to_type_obj(type_of_str):
    """
    convert builtins.typeOf result to NixType
    """
    return {
        "int": IntType(),
        "bool": BoolType(),
        "string": StrType(),
        "path": PathType(),
        "null": NullType(),
        "set": AttrsOfType(),
        "list": ListOfType(),
        "lambda": FunctionType(),
        "float": FloatType(),
    }[type_of_str]


class NixType(abc.ABC):
    pass


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class UnspecifiedType(NixType):
    pass


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class AnythingType(NixType):
    @property
    def child_type(self):
        return AnythingType()


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class BoolType(NixType):
    pass


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class IntType(NixType):
    minimum: int = None
    maximum: int = None


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class FloatType(NixType):
    minimum: float = None
    maximum: float = None


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class StrType(NixType):
    concatenated_with: str = None
    check: str = None
    legal_pattern: str = None


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class AttrsType(NixType):
    child_type = None


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class PathType(NixType):
    pass


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class PackageType(NixType):
    pass


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class FunctionType(NixType):
    return_type: NixType = None


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class ListOfType(NixType):
    child_type: NixType = None
    minimum: int = None
    maximum: int = None


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class AttrsOfType(NixType):
    child_type: NixType = AnythingType()
    lazy: bool = False


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class NullType(NixType):
    pass


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class SubmoduleType(NixType):
    child_type = AnythingType()


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class EitherType(NixType):
    subtypes: tuple = tuple()

    @property
    def child_type(self):
        possibilities = tuple(set([
            t.child_type
            for t in self.subtypes
            if hasattr(t, 'child_type')  # fix hack, shouldn't have ambiguous attributes
        ]))
        if possibilities:
            return EitherType(possibilities)
        else:
            raise TypeError("Attempted to get child types, but no Either.subtypes allow children.", self)


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class OneOfType(NixType):
    choices: tuple = tuple()


@dataclasses.dataclass(frozen=True, unsafe_hash=True)
class CoercedToType(EitherType):
    # "final_type or coerced_type convertible to it"
    final_type: NixType = AnythingType()
    coerced_type: NixType = AnythingType()

    subtypes: tuple = None

    def __post_init__(self):
        object.__setattr__(self, 'subtypes', (self.final_type, self.coerced_type))
