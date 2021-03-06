"""Implementation of special members of Python 2's abc library."""

from pytype import abstract
from pytype import overlay
from pytype import special_builtins


class ABCOverlay(overlay.Overlay):
  """A custom overlay for the 'abc' module."""

  def __init__(self, vm):
    member_map = {
        "abstractmethod": AbstractMethod,
        "abstractproperty": AbstractProperty
    }
    ast = vm.loader.import_name("abc")
    super(ABCOverlay, self).__init__(vm, "abc", member_map, ast)


class AbstractMethod(abstract.PyTDFunction):
  """Implements the @abc.abstractmethod decorator."""

  def __init__(self, name, vm):
    ast = vm.loader.import_name("abc")
    method = ast.Lookup("abc.abstractmethod")
    sigs = [abstract.PyTDSignature(name, sig, vm) for sig in method.signatures]
    super(AbstractMethod, self).__init__(name, sigs, method.kind, vm)

  def call(self, node, unused_func, args):
    """Marks that the given function is abstract."""
    self._match_args(node, args)

    # Since we have only 1 argument, it's easy enough to extract.
    if args.posargs:
      func_var = args.posargs[0]
    else:
      func_var = args.namedargs["function"]

    for func in func_var.data:
      if isinstance(func, (abstract.Function, abstract.BoundFunction)):
        func.is_abstract = True

    return node, func_var


class AbstractProperty(special_builtins.PropertyTemplate):
  """Implements the @abc.abstractproperty decorator."""

  def __init__(self, name, vm):
    super(AbstractProperty, self).__init__(vm, name, "abc")

  def call(self, node, funcv, args):
    property_args = self._get_args(args)
    for v in property_args.values():
      for b in v.bindings:
        f = b.data
        # If this check fails, we will raise a 'property object is not callable'
        # error down the line.
        # TODO(mdemello): This is in line with what python does, but we could
        # have a more precise error message that insisted f was a class method.
        if isinstance(f, abstract.Function):
          f.is_abstract = True
    cls = self.to_variable(node)
    return node, special_builtins.PropertyInstance(
        self.vm, self.name, cls, **property_args).to_variable(node)
