from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.api import DumpAnalyzer


@dataclass
class ModuleDefinition:
    """
    Describes a single debugger module contributed by a product team.

    Fields
    ------
    name : str
        Human-readable module name used in log output (e.g. "TagManager").
    analyzers : list[Callable]
        Ordered list of analyzer functions for this module.
        Each function must have the signature:
            def my_analyzer(analyzer: DumpAnalyzer) -> None
    """
    name      : str
    analyzers : list[Callable] = field(default_factory=list)


class ModuleRegistry:
    """
    Collects ModuleDefinitions registered by a product's product.py.
    Passed into product.register() by the engine — product teams never
    instantiate this directly.
    """

    def __init__(self):
        self._modules: list[ModuleDefinition] = []

    def register_module(self, module: ModuleDefinition) -> None:
        """
        Register a module with the engine.
        Modules are run in registration order.
        Raises ValueError if the same module name is registered twice.
        """
        if any(m.name == module.name for m in self._modules):
            raise ValueError(
                f"Module '{module.name}' is already registered. "
                f"Each module name must be unique within a product."
            )
        self._modules.append(module)

    # ── Engine-internal accessors (not part of the product-facing API) ─────────

    def _all_analyzers(self) -> list[tuple[str, Callable]]:
        """Returns [(module_name, analyzer_fn), ...] in registration order."""
        result = []
        for mod in self._modules:
            for fn in mod.analyzers:
                result.append((mod.name, fn))
        return result

    def _analyzer_map(self) -> dict[str, Callable]:
        """
        Returns {analyzer_fn_name: fn} for REPL 'run' command.
        If two modules define a function with the same name, the module
        name is prepended: "TagManager.analyze_occupied_tags".
        """
        seen_names: dict[str, int] = {}
        all_fns = [(mod.name, fn) for mod in self._modules for fn in mod.analyzers]

        # Count name collisions first
        for _, fn in all_fns:
            seen_names[fn.__name__] = seen_names.get(fn.__name__, 0) + 1

        result = {}
        for mod_name, fn in all_fns:
            key = f"{mod_name}.{fn.__name__}" if seen_names[fn.__name__] > 1 else fn.__name__
            result[key] = fn
        return result
