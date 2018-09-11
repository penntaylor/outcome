# -*- mode: python;-*-

# NOTES: This file looks big, but it's well under 100 loc if you omit docstrings.
#
# Outcome is a close cousin of Haskell's Either type, with Failure on the left
# and Success on the right. It is also a not-quite-a-monad, with `then` standing
# in for `bind`. There is no `join` (which doesn't seem terribly useful in Python).
# `return` is re-spelled `pureOutcome`, for obvious reasons.

from typing import Any, Callable, TypeVar, Union, Generic, Optional, Sequence, Iterator
from contextlib import contextmanager

L = TypeVar("L")  # The "left" side of the Either -- Failure's held type
R = TypeVar("R")  # The "right" side of the Either -- Success's held type
C = TypeVar("C")  # Return type of Callables

class Outcome(Generic[L, R]):
    """Base class describing outcome of a computation: Success or Failure.

    Functions returning an Outcome can be chained together so the
    chain stops at the first step returning Failure. This can be used
    to provide linear control flow for long sequences of operations that
    might fail at any step.

    The type annotations and `cast`s in the following examples are
    only required if using a typechecker. They can be omitted
    otherwise.

    Examples:

    # Since each step returns Success, the whole chain runs to the end:
    a:Outcome[str, int] = ( Success(1)
                            >> (lambda x: Success(x+1))
                            >> (lambda y: Success(y *3)) )
    print(isinstance(a, Success))
    # => True
    for value in onSuccess(a):
        print(value)
    # => 6

    # The second step returns Failure, so the computation stops there. Note
    # the `cast` operation; it's entirely to help the typechecker understand
    # our intent here.
    b:Outcome[str, int] = ( cast(Outcome[str, int], Success(1))
                            >> (lambda _: Failure("foo" ))
                            >> (lambda _: Success(0)) )
    print(isinstance(b, Success))
    # => False
    print(isinstance(b, Failure))
    # => True
    for reason in onFailure(b):
        print(reason)
    # => "foo"
    """
    def __init__(self) -> None:
        self.err:L
        self.val:R

    def then(self, f: Callable[[R], "Outcome[L, Any]"]) -> "Outcome[L, Any]":
        """Chains together computations that consume plain data and return an Outcome.

        In case of Failure, simply returns Failure.
        In case of Success, applies f to the value held by self.

        Args:
            f (Callable[[R], Outcome[L, Any]]): Function to apply to held value
              iff held value is a Success

        Returns:
            An Outcome; either f applied to held value of *this* Outcome, or the
              Failure that is *this* Outcome.

        Example:
        # Let a, b, c, and d be functions that consume an int and return
        # either Success or Failure:

        a(0).then(b).then(c).then(d)

        Computation will halt at the first function that returns a Failure.
        """
        if isinstance(self, Success):
            return f(self.val)
        else: # isinstance Failure
            return self

    def __rshift__(self, f: Callable[[R], "Outcome[L, Any]"]) -> "Outcome[L, Any]":
        """Infix version of `then` using `>>` operator.

        See documenation for `then`. This infix version should call to mind
        Haskell's `>>=` or FSharp's `|>`.

        Example from `then`, rewritten with `>>`:

        a(0) >> b >> c >> d
        """
        return self.then(f)


class Failure(Outcome[L, R]):
    """Intended for use as the return type of a computation to indicate failure.

    Property `reason` should explain the problem.

    Example:

    f = Failure("This failed because it couldn't succeed!")
    f.reason
    # => "This failed because it couldn't succeed!"
    """
    def __init__(self, reason:L) -> None:
        """Create a Failure with reason as the held value describing the failure.
        """
        self.err = reason

    @property
    def reason(self) -> L:
        """The reason for failure, which may be of any type.
        """
        return self.err

    def __repr__(self) -> str:
        return "(Failure, type={}, reason={})".format(type(self.reason), self.reason)


class Success(Outcome[L, R]):
    """Intended for use as the return type of a computation to indicate success.

    Property `value` contains the "result" of the computation.

    Example:

    s = Success(1234)
    s.value
    # => 1234
    """
    def __init__(self, v:R) -> None:
        """Create a Success with v as the held value.
        """
        self.val = v

    @property
    def value(self) -> R:
        """The held value. Can be of any type.
        """
        return self.val

    def __repr__(self) -> str:
        return "(Success, type={}, value={})".format(type(self.value), self.value)


def onFailure(oc:Outcome[L, R]) -> Iterator[L]:
    """Yields the reason of the failure, iff the thing failed
    """
    if isinstance(oc, Failure):
        yield oc.reason


def onSuccess(oc:Outcome[L, R]) -> Iterator[R]:
    """Yields the value of success, iff the thing succeeded
    """
    if isinstance(oc, Success):
        yield oc.value


def failed(oc:Outcome[L, R]) -> bool:
    """Returns True if oc is a Failure
    """
    if isinstance(oc, Failure):
        return True
    else:
        return False


def succeeded(oc:Outcome[L, R]) -> bool:
    """Returns True if oc is a Success
    """
    if isinstance(oc, Success):
        return True
    else:
        return False


def filterMapFailed(f: Callable[[L], C], ocs:Sequence[Outcome[L, R]]) -> Iterator[C]:
    """Yields values obtained by mapping f over **only** the Failures in ocs.

    NOTE: This is a filter followed by a map, so the returned iterator may have
    fewer elements than the input seqeuence
    """
    for oc in ocs:
        for reason in onFailure(oc):
            yield f(reason)


def filterMapSucceeded(f: Callable[[R], C], ocs:Sequence[Outcome[L, R]]) -> Iterator[C]:
    """Yields values obtained by mapping f over **only** the Successes in ocs.

    NOTE: This is a filter followed by a map, so the returned iterator may have
    fewer elements than the input seqeuence
    """
    for oc in ocs:
        for value in onSuccess(oc):
            yield f(value)


def pureOutcome(v:Any, sentinels:Sequence[Any]=[None], fstring:str="") -> Outcome:
    """Injects value v into an Outcome.

    Args:
        v: the value to inject into an Outcome

        sentinels: indicates which values to return as Failure;
        anything else is returned as Success.

        fstring: string to return as part of a Failure. This can be useful
        for notating where an injected value entered a computation.

    Returns:
        An Outcome. If Succcess, v is the held value. If Failure, the reason is
        a 2-tuple in which the first element is v, and the second is fstring.

    Notes:
        Use of this function may require obnoxious casts to satisfy typecheckers.
    """
    if v in sentinels:
        return Failure((v, fstring))
    else:
        return Success(v)


def liftOutcome(f: Callable[[R], C],
                sentinels:Sequence[Any]=[None],
                fstring:Optional[str]=None,
                catch=False) -> Callable[[R], Outcome[Any, C]]:
    """Transforms a function returning a value into a function returning an Outcome.

    Args:
        f: function to transform

        sentinels: indicates which values to return as Failure;
        anything else is returned as Success.

        fstring: string to return as part of a Failure. This can be useful
        for notating where an injected value entered a computation. If not provided,
        this will automatically be set to the __name__ of the function f.

        catch: indicates whether to silently catch Exceptions and return them
        as Failure. Default: False

    Returns:
        A wrapped function that returns an Outcome rather than a plain value.

    Notes:
        User of this function may require obnoxious casts to satisfy typecheckers.
    """
    if fstring is None: # Have to differentiate from empty string!
        myfstring = f.__name__
    else:
        myfstring = fstring
    if catch:
        return (lambda x: _exceptionWrapped(f, x, sentinels, myfstring))
    else:
        return (lambda x: pureOutcome(f(x), sentinels, myfstring))


def _exceptionWrapped(f: Callable[[R], C],
                      x:R,
                      sentinels:Sequence[Any],
                      fstring:str) -> Outcome[Any, C]:
    """Helper function for liftOutcome
    """
    try:
        return pureOutcome(f(x), sentinels, fstring)
    except Exception as e:
        return Failure((e, fstring))
