"""Tests for the analysis phase matcher (match_var_against_type)."""


from pytype import utils
from pytype.tests import test_base


class MatchTest(test_base.BaseTest):
  """Tests for matching types."""

  def testCallable(self):
    ty = self.Infer("""
      import tokenize
      def f():
        pass
      x = tokenize.generate_tokens(f)
    """)
    self.assertTypesMatchPytd(ty, """
      from typing import Generator, Tuple
      tokenize = ...  # type: module
      def f() -> NoneType
      x = ...  # type: Generator[Tuple[int, str, Tuple[int, int], Tuple[int, int], str], None, None]
    """)

  def testBoundAgainstCallable(self):
    ty = self.Infer("""
      import tokenize
      import StringIO
      x = tokenize.generate_tokens(StringIO.StringIO("").readline)
    """)
    self.assertTypesMatchPytd(ty, """
      from typing import Generator, Tuple
      tokenize = ...  # type: module
      StringIO = ...  # type: module
      x = ...  # type: Generator[Tuple[int, str, Tuple[int, int], Tuple[int, int], str], None, None]
    """)

  def testTypeAgainstCallable(self):
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", """
        from typing import Callable
        def f(x: Callable) -> str
      """)
      ty = self.Infer("""
        import foo
        def f():
          return foo.f(int)
      """, pythonpath=[d.path])
      self.assertTypesMatchPytd(ty, """
        foo = ...  # type: module
        def f() -> str
      """)

  def testMatchStatic(self):
    ty = self.Infer("""
      s = {1}
      def f(x):
        # set.intersection is a static method:
        return s.intersection(x)
    """)
    self.assertTypesMatchPytd(ty, """
      from typing import Set
      s = ...  # type: Set[int]

      def f(x) -> set: ...
    """)

  def testGenericHierarchy(self):
    with utils.Tempdir() as d:
      d.create_file("a.pyi", """
        from typing import Iterable
        def f(x: Iterable[str]) -> str
      """)
      ty = self.Infer("""
        import a
        x = a.f(["a", "b", "c"])
      """, pythonpath=[d.path])
      self.assertTypesMatchPytd(ty, """
        a = ...  # type: module
        x = ...  # type: str
      """)

  def testEmpty(self):
    ty = self.Infer("""
      a = []
      b = ["%d" % i for i in a]
    """)
    self.assertTypesMatchPytd(ty, """
      from typing import Any, List
      a = ...  # type: List[nothing]
      b = ...  # type: List[str]
      i = ...  # type: Any
    """)

  def testGeneric(self):
    with utils.Tempdir() as d:
      d.create_file("a.pyi", """
        from typing import Generic, Iterable
        K = TypeVar("K")
        V = TypeVar("V")
        Q = TypeVar("Q")
        class A(Iterable[V], Generic[K, V]): ...
        class B(A[K, V]):
          def __init__(self):
            self := B[bool, str]
        def f(x: Iterable[Q]) -> Q
      """)
      ty = self.Infer("""
        import a
        x = a.f(a.B())
      """, deep=False, pythonpath=[d.path])
      self.assertTypesMatchPytd(ty, """
        a = ...  # type: module
        x = ...  # type: str
      """)

  def testMatchIdentityFunction(self):
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", """
        from typing import TypeVar
        T = TypeVar("T")
        def f(x: T) -> T: ...
      """)
      ty = self.Infer("""
        import foo
        v = foo.f(__any_object__)
      """, pythonpath=[d.path])
      self.assertTypesMatchPytd(ty, """
        from typing import Any
        foo = ...  # type: module
        v = ...  # type: Any
      """)

  def testNoArgumentPyTDFunctionAgainstCallable(self):
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", """
        def bar() -> bool
      """)
      _, errors = self.InferWithErrors("""\
        from __future__ import google_type_annotations
        from typing import Callable
        import foo

        def f(x: Callable[[], int]): ...
        def g(x: Callable[[], str]): ...

        f(foo.bar)  # ok
        g(foo.bar)
      """, pythonpath=[d.path])
      self.assertErrorLogIs(errors, [(9, "wrong-arg-types",
                                      r"\(x: Callable\[\[\], str\]\).*"
                                      r"\(x: Callable\[\[\], bool\]\)")])

  def testPyTDFunctionAgainstCallableWithTypeParameters(self):
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", """
        def f1(x: int) -> int: ...
        def f2(x: int) -> bool: ...
        def f3(x: int) -> str: ...
      """)
      _, errors = self.InferWithErrors("""\
        from __future__ import google_type_annotations
        from typing import Callable, TypeVar
        import foo

        T_plain = TypeVar("T_plain")
        T_constrained = TypeVar("T_constrained", int, bool)
        def f1(x: Callable[[T_plain], T_plain]): ...
        def f2(x: Callable[[T_constrained], T_constrained]): ...

        f1(foo.f1)  # ok
        f1(foo.f2)  # ok
        f1(foo.f3)
        f2(foo.f1)  # ok
        f2(foo.f2)
        f2(foo.f3)
      """, pythonpath=[d.path])
      expected = r"Callable\[\[Union\[bool, int\]\], Union\[bool, int\]\]"
      self.assertErrorLogIs(errors, [
          (12, "wrong-arg-types",
           r"Expected.*Callable\[\[str\], str\].*"
           r"Actual.*Callable\[\[int\], str\]"),
          (14, "wrong-arg-types",
           r"Expected.*Callable\[\[bool\], bool\].*"
           r"Actual.*Callable\[\[int\], bool\]"),
          (15, "wrong-arg-types",
           r"Expected.*" + expected + ".*"
           r"Actual.*Callable\[\[int\], str\]")])

  def testInterpreterFunctionAgainstCallable(self):
    _, errors = self.InferWithErrors("""\
      from __future__ import google_type_annotations
      from typing import Callable
      def f(x: Callable[[bool], int]): ...
      def g1(x: int) -> bool:
        return __any_object__
      def g2(x: str) -> int:
        return __any_object__
      f(g1)  # ok
      f(g2)
    """)
    self.assertErrorLogIs(errors, [(9, "wrong-arg-types",
                                    r"Expected.*Callable\[\[bool\], int\].*"
                                    r"Actual.*Callable\[\[str\], int\]")])

  def testBoundInterpreterFunctionAgainstCallable(self):
    _, errors = self.InferWithErrors("""\
      from __future__ import google_type_annotations
      from typing import Callable

      class A(object):
        def f(self, x: int) -> bool:
          return __any_object__
      unbound = A.f
      bound = A().f

      def f1(x: Callable[[bool], int]): ...
      def f2(x: Callable[[A, bool], int]): ...
      def f3(x: Callable[[bool], str]): ...

      f1(bound)  # ok
      f2(bound)
      f3(bound)
      f1(unbound)
      f2(unbound)  # ok
    """)
    self.assertErrorLogIs(errors, [(15, "wrong-arg-types",
                                    r"Expected.*Callable\[\[A, bool\], int\].*"
                                    r"Actual.*Callable\[\[int\], bool\]"),
                                   (16, "wrong-arg-types",
                                    r"Expected.*Callable\[\[bool\], str\].*"
                                    r"Actual.*Callable\[\[int\], bool\]"),
                                   (17, "wrong-arg-types",
                                    r"Expected.*Callable\[\[bool\], int\].*"
                                    r"Actual.*Callable\[\[Any, int\], bool\]")])

  def testCallableParameters(self):
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", """
        from typing import Any, Callable, List, TypeVar
        T = TypeVar("T")
        def f1(x: Callable[..., T]) -> List[T]: ...
        def f2(x: Callable[[T], Any]) -> List[T]: ...
      """)
      ty = self.Infer("""\
        from __future__ import google_type_annotations
        from typing import Any, Callable
        import foo

        def g1(): pass
        def g2() -> int: pass
        v1 = foo.f1(g1)
        v2 = foo.f1(g2)

        def g3(x): pass
        def g4(x: int): pass
        w1 = foo.f2(g3)
        w2 = foo.f2(g4)
      """, deep=False, pythonpath=[d.path])
      self.assertTypesMatchPytd(ty, """
        from typing import Any, List
        foo = ...  # type: module
        def g1() -> Any: ...
        def g2() -> int: ...
        def g3(x) -> Any: ...
        def g4(x: int) -> Any: ...

        v1 = ...  # type: list
        v2 = ...  # type: List[int]
        w1 = ...  # type: list
        w2 = ...  # type: List[int]
      """)

  def testVariableLengthFunctionAgainstCallable(self):
    _, errors = self.InferWithErrors("""\
      from __future__ import google_type_annotations
      from typing import Any, Callable
      def f(x: Callable[[int], Any]): pass
      def g1(x: int=0): pass
      def g2(x: str=""): pass
      f(g1)  # ok
      f(g2)
    """)
    self.assertErrorLogIs(errors, [(7, "wrong-arg-types",
                                    r"Expected.*Callable\[\[int\], Any\].*"
                                    r"Actual.*Callable\[\[str\], Any\]")])

  def testCallableInstanceAgainstCallableWithTypeParameters(self):
    _, errors = self.InferWithErrors("""\
      from __future__ import google_type_annotations
      from typing import Callable, TypeVar
      T = TypeVar("T")
      def f(x: Callable[[T], T]): ...
      def g() -> Callable[[int], str]: return __any_object__
      f(g())
    """)
    self.assertErrorLogIs(errors, [(6, "wrong-arg-types",
                                    r"Expected.*Callable\[\[str\], str\].*"
                                    r"Actual.*Callable\[\[int\], str\]")])

  def testFunctionWithTypeParameterArgAgainstCallable(self):
    self.Check("""\
      from __future__ import google_type_annotations
      from typing import Any, AnyStr, Callable, TypeVar
      T = TypeVar("T")
      MyAnyStr = TypeVar("MyAnyStr", unicode, str)
      def f(x: Callable[[AnyStr], Any]): ...
      def g1(x: AnyStr) -> AnyStr: return x
      def g2(x: T) -> T: return x
      def g3(x: MyAnyStr) -> MyAnyStr: return x

      f(g1)  # ok: same parameter
      f(g2)  # ok: callable parameters are contravariant, g2 is more general
      f(g3)  # ok: constraints match
    """)

  def testFunctionWithTypeParameterReturnAgainstCallable(self):
    _, errors = self.InferWithErrors("""\
      from __future__ import google_type_annotations
      from typing import Callable, AnyStr, TypeVar
      T = TypeVar("T")
      def f(x: Callable[..., AnyStr]): ...
      def g1(x: AnyStr) -> AnyStr: return x
      def g2(x: T) -> T: return x

      f(g1)  # ok
      f(g2)
    """)
    self.assertErrorLogIs(errors, [(9, "wrong-arg-types")])

  def testUnionInTypeParameter(self):
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", """
        from typing import Callable, Iterator, List, TypeVar
        T = TypeVar("T")
        def decorate(func: Callable[..., Iterator[T]]) -> List[T]
      """)
      ty = self.Infer("""
        from __future__ import google_type_annotations
        from typing import Generator, Optional
        import foo
        @foo.decorate
        def f() -> Generator[Optional[str]]:
          yield "hello world"
      """, deep=False, pythonpath=[d.path])
      self.assertTypesMatchPytd(ty, """
        from typing import List, Optional
        foo = ...  # type: module
        f = ...  # type: List[Optional[str]]
      """)

  def testAnyStr(self):
    self.Check("""
      from __future__ import google_type_annotations
      from typing import AnyStr, Dict, Tuple
      class Foo(object):
        def bar(self, x: Dict[Tuple[AnyStr], AnyStr]): ...
    """)

  def testFormalType(self):
    _, errors = self.InferWithErrors("""\
      from __future__ import google_type_annotations
      from typing import AnyStr, List, NamedTuple
      def f(x: str):
        pass
      f(AnyStr)
      def g(x: List[str]):
        pass
      g([AnyStr])
      H = NamedTuple("H", [('a', AnyStr)])
    """)
    self.assertErrorLogIs(errors, [
        (5, "invalid-typevar"),
        (8, "invalid-typevar"),
        (9, "invalid-typevar")])

  def testCallableReturn(self):
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", """
        from typing import Callable, TypeVar
        T = TypeVar("T")
        def foo(func: Callable[[], T]) -> T: ...
      """)
      self.Check("""
        import foo
        class Foo(object):
          def __init__(self):
            self.x = 42
        foo.foo(Foo).x
      """, pythonpath=[d.path])

  def testCallableUnionReturn(self):
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", """
        from typing import Callable, TypeVar
        T1 = TypeVar("T1")
        T2 = TypeVar("T2")
        def foo(func: Callable[[], T1]) -> T1 or T2: ...
      """)
      self.Check("""
        import foo
        class Foo(object):
          def __init__(self):
            self.x = 42
        v = foo.foo(Foo)
        if isinstance(v, Foo):
          v.x
      """, pythonpath=[d.path])

  def testTypeVarWithBound(self):
    _, errors = self.InferWithErrors("""\
      from __future__ import google_type_annotations
      from typing import Callable, TypeVar
      T1 = TypeVar("T1", bound=int)
      T2 = TypeVar("T2")
      def f(x: T1) -> T1:
        return __any_object__
      def g(x: Callable[[T2], T2]) -> None:
        pass
      g(f)  # line 9
    """)
    self.assertErrorLogIs(errors, [(9, "wrong-arg-types",
                                    r"Expected.*T2.*Actual.*T1")])

  def testCallableBaseClass(self):
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", """
        from typing import Callable, Union, Type
        def f() -> Union[Callable[[], ...], Type[Exception]]
        def g() -> Union[Type[Exception], Callable[[], ...]]
      """)
      self.Check("""
        from __future__ import google_type_annotations
        from typing import Union
        import foo
        class Foo(foo.f()):
          pass
        class Bar(foo.g()):
          pass
        def f(x: Foo, y: Bar) -> Union[Bar, Foo]:
          return x or y
        f(Foo(), Bar())
      """, pythonpath=[d.path])

  def testAnyBaseClass(self):
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", """
        from typing import Any
        class Foo(Any): pass
        class Bar(object): pass
        def f(x: Bar) -> None
      """)
      self.Check("""
        import foo
        foo.f(foo.Foo())
      """, pythonpath=[d.path])

  def testMaybeParameterized(self):
    self.Check("""
      import collections
      class Foo(collections.MutableMapping):
        pass
      dict.__delitem__(Foo(), __any_object__)  # pytype: disable=wrong-arg-types
    """)

  def testCallableAgainstGeneric(self):
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", """
        from typing import TypeVar, Callable, Generic, Iterable, Iterator
        A = TypeVar("A")
        N = TypeVar("N")
        class Foo(Generic[A]):
          def __init__(self, c: Callable[[], N]):
            self := Foo[N]
        x = ...  # type: Iterator[int]
      """)
      self.Check("""
        import foo
        foo.Foo(foo.x.next)
      """, pythonpath=[d.path])

  def testTypeVarAgainstTypeVar(self):
    _, errors = self.InferWithErrors("""\
      from __future__ import google_type_annotations
      from typing import Any, Callable, TypeVar
      T1 = TypeVar("T1")
      T2 = TypeVar("T2", bound=str)
      T3 = TypeVar("T3", bound=basestring)
      T4 = TypeVar("T4", bound=int)
      T5 = TypeVar("T5", str, unicode)
      T6 = TypeVar("T6", int, float)
      T7 = TypeVar("T7", int, float, complex)
      def f1(x: T1, y: T1) -> None: pass
      def f2(x: T2, y: T2) -> None: pass
      def f3(x: T3, y: T3) -> None: pass
      def f4(x: T4, y: T4) -> None: pass
      def f5(x: T5, y: T5) -> None: pass
      def f6(x: T6, y: T6) -> None: pass
      def f7(x: T7, y: T7) -> None: pass
      def g1(x: Callable[[T1, T1], None]) -> None: pass
      def g2(x: Callable[[T2, T2], None]) -> None: pass
      def g3(x: Callable[[T3, T3], None]) -> None: pass
      def g4(x: Callable[[T4, T4], None]) -> None: pass
      def g5(x: Callable[[T5, T5], None]) -> None: pass
      def g6(x: Callable[[T6, T6], None]) -> None: pass
      def g7(x: Callable[[T7, T7], None]) -> None: pass
      # below, gN(fM) causes N to be matched against M
      g1(f1)  # ok: same TypeVar
      g2(f1)  # ok: T2 has a bound, T1 doesn't
      g5(f1)  # ok: T5 has constraints, T1 doesn't
      g2(f2)  # ok: same TypeVar
      g4(f2)  # error, line 29
      g5(f2)  # error, line 30
      g6(f2)  # error, line 31
      g5(f3)  # ok: T5 has contraints within the bound of T3
      g5(f4)  # error, line 33
      g6(f5)  # error, line 34
      g6(f7)  # ok: T6 constraints are a subset of T7
      g7(f6)  # error, line 36
    """)
    self.assertErrorLogIs(errors, [
        (29, "wrong-arg-types", "T4.*T2"),
        (30, "wrong-arg-types", "T5.*T2"),
        (31, "wrong-arg-types", "T6.*T2"),
        (33, "wrong-arg-types", "T5.*T4"),
        (34, "wrong-arg-types", "T6.*T5"),
        (36, "wrong-arg-types", "T7.*T6"),
    ])


if __name__ == "__main__":
  test_base.main()
