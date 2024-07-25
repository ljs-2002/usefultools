import inspect

from abc import get_cache_token
from functools import update_wrapper
from types import GenericAlias
from typing import Iterable, get_type_hints

__all__ = ['multi_dispatch']

IGNORE_TYPE = inspect._empty

################################################################################
### copy from functools
################################################################################

def _c3_merge(sequences):
    """Merges MROs in *sequences* to a single MRO using the C3 algorithm.

    Adapted from https://www.python.org/download/releases/2.3/mro/.

    """
    result = []
    while True:
        sequences = [s for s in sequences if s]   # purge empty sequences
        if not sequences:
            return result
        for s1 in sequences:   # find merge candidates among seq heads
            candidate = s1[0]
            for s2 in sequences:
                if candidate in s2[1:]:
                    candidate = None
                    break      # reject the current head, it appears later
            else:
                break
        if candidate is None:
            raise RuntimeError("Inconsistent hierarchy")
        result.append(candidate)
        # remove the chosen candidate
        for seq in sequences:
            if seq[0] == candidate:
                del seq[0]

def _c3_mro(cls, abcs=None):
    """Computes the method resolution order using extended C3 linearization.

    If no *abcs* are given, the algorithm works exactly like the built-in C3
    linearization used for method resolution.

    If given, *abcs* is a list of abstract base classes that should be inserted
    into the resulting MRO. Unrelated ABCs are ignored and don't end up in the
    result. The algorithm inserts ABCs where their functionality is introduced,
    i.e. issubclass(cls, abc) returns True for the class itself but returns
    False for all its direct base classes. Implicit ABCs for a given class
    (either registered or inferred from the presence of a special method like
    __len__) are inserted directly after the last ABC explicitly listed in the
    MRO of said class. If two implicit ABCs end up next to each other in the
    resulting MRO, their ordering depends on the order of types in *abcs*.

    """
    for i, base in enumerate(reversed(cls.__bases__)):
        if hasattr(base, '__abstractmethods__'):
            boundary = len(cls.__bases__) - i
            break   # Bases up to the last explicit ABC are considered first.
    else:
        boundary = 0
    abcs = list(abcs) if abcs else []
    explicit_bases = list(cls.__bases__[:boundary])
    abstract_bases = []
    other_bases = list(cls.__bases__[boundary:])
    for base in abcs:
        if issubclass(cls, base) and not any(
                issubclass(b, base) for b in cls.__bases__
            ):
            # If *cls* is the class that introduces behaviour described by
            # an ABC *base*, insert said ABC to its MRO.
            abstract_bases.append(base)
    for base in abstract_bases:
        abcs.remove(base)
    explicit_c3_mros = [_c3_mro(base, abcs=abcs) for base in explicit_bases]
    abstract_c3_mros = [_c3_mro(base, abcs=abcs) for base in abstract_bases]
    other_c3_mros = [_c3_mro(base, abcs=abcs) for base in other_bases]
    return _c3_merge(
        [[cls]] +
        explicit_c3_mros + abstract_c3_mros + other_c3_mros +
        [explicit_bases] + [abstract_bases] + [other_bases]
    )

def _compose_mro(cls, types):
    """Calculates the method resolution order for a given class *cls*.

    Includes relevant abstract base classes (with their respective bases) from
    the *types* iterable. Uses a modified C3 linearization algorithm.

    """
    bases = set(cls.__mro__)
    # Remove entries which are already present in the __mro__ or unrelated.
    def is_related(typ):
        return (typ not in bases and hasattr(typ, '__mro__')
                                 and not isinstance(typ, GenericAlias)
                                 and issubclass(cls, typ))
    types = [n for n in types if is_related(n)]
    # Remove entries which are strict bases of other entries (they will end up
    # in the MRO anyway.
    def is_strict_base(typ):
        for other in types:
            if typ != other and typ in other.__mro__:
                return True
        return False
    types = [n for n in types if not is_strict_base(n)]
    # Subclasses of the ABCs in *types* which are also implemented by
    # *cls* can be used to stabilize ABC ordering.
    type_set = set(types)
    mro = []
    for typ in types:
        found = []
        for sub in typ.__subclasses__():
            if sub not in bases and issubclass(cls, sub):
                found.append([s for s in sub.__mro__ if s in type_set])
        if not found:
            mro.append(typ)
            continue
        # Favor subclasses with the biggest number of useful bases
        found.sort(key=len, reverse=True)
        for sub in found:
            for subcls in sub:
                if subcls not in mro:
                    mro.append(subcls)
    return _c3_mro(cls, abcs=mro)

################################################################################
### end copy from functools
################################################################################

class Node:
    def __init__(self, value):
        self.value = value
        self.children = []
        self.seq = None
    
    def add_child(self, child):
        self.children.append(child)
    
    def get(self, value):
        if isinstance(value, Iterable):
            child = [c for c in self.children if c in value]
            if child:
                return child[0]
        else:
            if value in self:
                return self.children[self.children.index(value)]
        return None

    def set_seq(self, seq):
        self.seq = seq

    def __eq__(self,other):
        if self.value == IGNORE_TYPE:
            return True
        if isinstance(other, Node):
            if  other.value == IGNORE_TYPE:
                return True
            return self.value == other.value
        if other == IGNORE_TYPE:
            return True
        return other == self.value

    def __contains__(self, value):
        return value in self.children

class TypeTree:
    def __init__(self, types:list[tuple]):
        self.root = Node(None)
        self.build_tree(types)

    def add_type(self, types:tuple):
        current = self.root
        for part in types:
            found = False
            if part in current:
                current = current.get(part)
                found = True
            
            if not found:
                new_node = Node(part)
                current.add_child(new_node)
                current = new_node
            
        current.set_seq(types)

    def build_tree(self, types:list[tuple]):
        for types in types:
            self.add_type(types)

    def clear(self):
        self.root = Node(None)

    def __getitem__(self, types:list[list]):
        current = self.root
        for typ in types:
            current = current.get(typ)
            if not current:
                return object
        return current.seq

def _find_impl(cls, registry, types_cache:TypeTree):
    """Returns the best matching implementation from *registry* for type *cls*.

    Where there is no registered implementation for a specific type, its method
    resolution order is used to find a more generic implementation.

    Note: if *registry* does not contain an implementation for the base
    *object* type, this function may return None.

    """
    typs = [typ for typ in registry.keys() if typ != object]
    typs = set(t for ts in typs for t in ts)
    mro = [_compose_mro(c, typs) for c in cls]
    match = types_cache[mro]
    return registry.get(match)

def _get_args_type(func):
    signature = inspect.signature(func)

    # 获取参数及其类型
    parameters = signature.parameters
    type_hints = get_type_hints(func)
    
    return tuple(type_hints.get(param_name, param.annotation) for param_name, param in parameters.items())

def multi_dispatch(func):
    """Multi-dispatch generic function decorator.

    Transforms a function into a generic function, which can have different
    behaviours depending upon the type of its argument. The decorated
    function acts as the default implementation, and additional
    implementations can be registered using the register() attribute of the
    generic function.
    """
    import types, weakref

    registry = {}
    dispatch_cache = weakref.WeakKeyDictionary()
    cache_token = None
    types_cache = TypeTree([])

    def dispatch(cls):
        """generic_func.dispatch(cls) -> <function implementation>

        Runs the dispatch algorithm to return the best available implementation
        for the given *cls* registered on *generic_func*.

        """
        nonlocal cache_token, types_cache
        if cache_token is not None:
            current_token = get_cache_token()
            if cache_token != current_token:
                dispatch_cache.clear()
                cache_token = current_token
        try:
            impl = dispatch_cache[cls]
        except KeyError:
            try:
                impl = registry[cls]
            except KeyError:
                impl = _find_impl(cls, registry,types_cache)
            dispatch_cache[cls] = impl
        return impl

    def _is_valid_dispatch_type(cls):
        return isinstance(cls, type) and not isinstance(cls, GenericAlias)

    def register(func=None,force=False):
        """
        Register a multi-dispatch function for the type of the argument of func.
        Override the existing function if force is True.
        """
        nonlocal cache_token, types_cache
        if func is None:
            return lambda f: register(f,force)
        cls = _get_args_type(func)
        if not force and cls in registry:
            raise TypeError(
                f"Function {func!r} already registered for {cls!r}. "
                f"Use force=True to override."
                )
        
        if any(not _is_valid_dispatch_type(c) for c in cls):
            if func is not None:
                raise TypeError(
                    f"Invalid first argument to `register()`. "
                    f"{cls!r} is not a class."
                )

        registry[cls] = func
        types_cache.add_type(cls)
        if cache_token is None and any(hasattr(c, '__abstractmethods__') for c in cls):
            cache_token = get_cache_token()
        dispatch_cache.clear()
        return func

    def wrapper(*args, **kw):
        if not args:
            raise TypeError(f'{funcname} requires at least '
                            '1 positional argument')
        cls = (arg.__class__ for arg in args)
        return dispatch(cls)(*args, **kw)

    funcname = getattr(func, '__name__', 'multidispatch function')
    registry[object] = func
    wrapper.register = register
    wrapper.dispatch = dispatch
    wrapper.registry = types.MappingProxyType(registry)
    wrapper._clear_cache = dispatch_cache.clear
    update_wrapper(wrapper, func)
    return wrapper