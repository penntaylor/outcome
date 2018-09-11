# outcome
Chain potentially fallible computations without having to check return values at each step

# Motivation, TL;DR version
Did-it-fail-before-I-continue-conditional-testing hell, like this:
```python
first = foo(9)
if first:
    second = bar(first)
    if second:
        third = baz(second)
        if third:
           print("Computation chain succeeded: {}".format(third))
        else:
            print("baz failed")
    else:
        print("bar failed")
else:
    print("foo failed")
```
becomes this:
```python
result = foo(9) >> bar >> baz

for value in onSuccess(result):
    print("Computation chain succeeded: {}".format(value))

for reason in onFailure(result):
    print(reason)
```
The `>>` infix operator should remind Haskellers of `>>=`, and
FSharpers of `|>`. It can also be spelled as an instance method
of `Outcome`, `.then()`. These two are equivalent:

```python
result = foo(9) >> bar >> baz
result = foo(9).then(bar).then(baz)
```

# Motivation, Director's Extended Cut
It's common in some problem domains to have a long sequence of
transforms over a set of data, in which any transform in the series
might fail and the computation should be stopped at that point.

One approach to this situation is to use conditional branching,
inspecting the return value of each step along the way and stopping
when the "failure" sentinel value appears.  If the sequence of
transforms is long, conditional branching can lead to noisy code that
obscures the core logic. Often you can't use the same sentinel value
for every step along the way, and the "did it fail?" conditions become
easy-to-break code.

Another approach is to have each computation step raise an exception
upon failure, and wrap the larger chain in a `try...except` block.
Exceptions don't always seem to fit, though: if failure of a
computation is "normal", then by definition it isn't *exceptional*, so
raising an exception seems conceptually wrong. Client code calling
into any individual function that is part of the chain will also have
to be prepared to handle an exception that may otherwise halt the
program.

In the functional paradigm, exceptions are usually a poor fit,
and lots of conditional branching can quickly turn functional code
into imperative code.

Outcome is one way to address the shortcomings of conditional
branching and exceptions for these situations, and it plays nicely
with code written in the functional paradigm.

Consider a sequence of computations that could fail:

```python
# These implicitly return `None` as a sentinel to indicate a failed
# operation.

def foo(a):
    if a < 10:
        return a + 1

def bar(b):
    if b > 8:
        return b - 1

def baz(c):
    if c % 2 == 0:
        return c
```

A "chained" sequence of these functions using conditional branching
looks like this:
```python
first = foo(9)
if first:
    second = bar(first)
    if second:
        third = baz(second)
        if third:
           print("Computation chain succeeded: {}".format(third))
        else:
            print("baz failed")
    else:
        print("bar failed")
else:
    print("foo failed")

# => baz failed
```

If the functions are rewritten to return a `Success` or `Failure`
subclass of `Outcome`, the "chaining" logic becomes:

```python
from outcome import onSuccess, onFailure

result = foo(9) >> bar >> baz

for value in onSuccess(result):
    print("Computation chain succeeded: {}".format(value))

for reason in onFailure(result):
    print(reason)

# => baz failed
```

Okay, so how do the functions have to be written to support this?
It's pretty simple; they just need to explcitly return a `Success` or
`Failure` `Outcome` rather than raw values or implicit `None`:

```python
# Notice that we now return an explicit `Failure` type rather than
# relying on an implicit `None` as a sentinel.

def foo(a):
    if a < 10:
        return Success(a + 1)
    else:
        return Failure("foo failed")

def bar(b):
    if b > 8:
        return Success(b - 1)
    else:
        return Failure("bar failed")

def baz(c):
    if c % 2 == 0:
        return Success(c)
    else:
        return Failure("baz failed")

```

The following convenience functions are also included:
* failed
* succeeeded
* filterMapFailed
* filterMapSucceeded

The first two, `failed` and `succeeded` are handy for conditionally
branching on the success or failure of a result when all you care
about is *whether* the whole chain ran to completion; that is, you
don't care about what is *inside* the result. This is great for long
chains that end in File IO, when all you want to know is whether the
thing was written to disk at the end.

The next two, `filterMapFailed` and `filterMapSucceeded` are useful
for mapping an operation over a `Sequence` of `Outcome`s, when you
only want the operation to apply to one type of `Outcome`. For
example, say you have a list of `Outcome`s called `my_outcomes`
corresponding to some file operation that might fail. The `Success`es
contain the name of the file, and the `Failure`s contain the exception
raised when the operation failed. You might then want to do something
like this:

```python
# get a list of every file that succeeded
theseWorked = list(filterMapSucceeded(lambda f: f, my_outcomes))

# log the exception for every file that failed
list(filterMapFailed(lambda e: logging.error(e), my_outcomes))
```

Notice in the example for `filterMapFailed` we converted to a `list`
even though we weren't storing the value. `filterMapFailed` and
`filterMapSucceeded` both return iterators -- which is nice because it
allows for lazy evaluation -- so we have to use some outer operation
to fully consume the iterator to ensure the lambda gets applied to all
appropriate elements in `my_outcomes`. `list` works fine for this in a
pinch, but if you find yourself doing this a lot, I highly recommend
looking at the "recipes" in the `itertools` standard library and
adding something like the `consume` function found there to your own
bag of tricks.

# Looks interesting, but I'm not going to rewrite all my functions to return Outcomes

I hear you: you have working code that you don't want to mess up or
refactor just to try this out. Or maybe you want the exposed functions
of your library to be "vanilla" python, but you think it might be nice
to use `Outcome` internally for chaining. Or maybe you want to use
`Outcome` with a third-party library and don't want to have to wrap
each and every function.

No problem. The functions `pureOutcome` and `liftOutcome` are provided
for exactly these situations. `pureOutcome` can be used to turn a
*value* into an appropriate `Outcome` so you can send it into a
computation chain. `liftOutcome` turns a *function returning a normal
value* into a *function returning an `Outcome`*. Remember the original
versions of `foo` and `bar` up there, the ones that return either an
`int` or a `None`?  We can turn them into `Outcome`s on the fly:

```python
result = pureOutcome(foo(9)) >> liftOutcome(bar) >> liftOutcome(baz)
```

See the docstrings for `pureOutcome` and `liftOutcome`; they contain
additional information that is important for correct use. Pay special
attention to the shape of the `reason` held by `Failure` when using
these injections.

For those using a typechecker, it's important to recognize it is not
generally possible to have a narrow, type-stable Left (Failure) when
using pureOutcome and liftOutcome, due to the necessity of allowing
*anything* to be used as a sentinel. You're pretty much stuck with
`Any` as the type of `Failure.reason` when using these two functions.
