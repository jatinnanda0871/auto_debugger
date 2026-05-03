from engine.registry import ModuleRegistry, ModuleDefinition
from products.epdc.modules.tag_manager.analyzers import analyze_occupied_tags
from products.epdc.modules.fcc_manager.analyzers import analyze_fcc_counter


def register(registry: ModuleRegistry) -> None:
    registry.register_module(ModuleDefinition(
        name      = "TagManager",
        analyzers = [analyze_occupied_tags],
    ))

    registry.register_module(ModuleDefinition(
        name      = "FccManager",
        analyzers = [analyze_fcc_counter],
    ))
