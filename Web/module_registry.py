from typing import Dict, Any

class ModuleRegistry:
    def __init__(self):
        self._modules: Dict[str, Any] = {}
        self._path_matchers = {}

    def register(self, name: str, settings_bool, path_matcher=lambda path: False):
        self._modules[name] = settings_bool
        self._path_matchers[name] = path_matcher

    def is_enabled(self, name: str) -> bool:
        if name not in self._modules:
            return False
        return bool(self._modules[name])

    def get_all_status(self) -> Dict[str, bool]:
        return {name: bool(sys_bool) for name, sys_bool in self._modules.items()}

    def get_module_for_path(self, path: str) -> str:
        for name, matcher in self._path_matchers.items():
            if self.is_enabled(name) and matcher(path):
                return name
        return None

registry = ModuleRegistry()
