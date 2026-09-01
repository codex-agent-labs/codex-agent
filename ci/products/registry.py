from __future__ import annotations

from dataclasses import dataclass

from .contract_model import CONTRACT_COMPONENTS
from .receipt import PHASES as RECEIPT_PHASES
from .receipt import PRODUCTS


PHASE_ORDER = ("binary", "package", "validation", "metadata")
VERSION_IDENTITIES = {
    "contract",
    "runtime-compatibility",
    "runtime-release",
    "sdk",
}
NATIVE_TARGETS = (
    "linux-arm64",
    "linux-x64",
    "macos-arm64",
    "macos-x64",
    "windows-x64",
)
RUNTIME_ADAPTERS = ("jvm", "node-js", "node-wasm")
RUNTIME_COMPONENTS = tuple(sorted((*NATIVE_TARGETS, *RUNTIME_ADAPTERS)))
NATIVE_BINDINGS = ("cpp", "csharp", "dart", "python", "rust")
BINDING_COMPONENTS = (*NATIVE_BINDINGS, "javascript")
SDK_COMPATIBILITY_COMPONENTS = ("sdk-core", "sdk-android", "sdk-ios", *BINDING_COMPONENTS)
# Index coordinates identify the public product/package family. Per-target Maven
# modules, classifiers, and release assets remain exact receipt outputs instead
# of competing coordinate identities for one logical component.
PUBLISHED_COORDINATES = {
    ("contract", "contract"): "io.github.codex-agent-labs:codex-agent-core",
    **{
        ("runtime", component): "io.github.codex-agent-labs:codex-agent-runtime-desktop"
        for component in (*RUNTIME_COMPONENTS, "runtime-aggregate")
    },
    ("sdk", "sdk-core"): "io.github.codex-agent-labs:codex-agent",
    ("sdk", "sdk-android"): "io.github.codex-agent-labs:codex-agent-runtime-android",
    ("sdk", "sdk-ios"): "io.github.codex-agent-labs:codex-agent-runtime-ios",
    ("sdk", "javascript"): "@codex-agent-labs/codex-agent",
    ("sdk", "python"): "codex-agent",
    ("sdk", "csharp"): "CodexAgent",
    ("sdk", "rust"): "codex-agent",
    ("sdk", "cpp"): "CodexAgent::CodexAgent",
    ("sdk", "dart"): "codex_agent",
}
SDK_FACADE_TARGETS = (
    "android",
    "ios-arm64",
    "ios-simulator-arm64",
    "jvm",
    "linux-arm64",
    "linux-x64",
    "macos-arm64",
    "macos-x64",
    "node-js",
    "node-wasm",
    "windows-x64",
)
SDK_FACADE_CONTRACT_COMPONENTS = {
    target: target for target in SDK_FACADE_TARGETS
}


@dataclass(frozen=True, order=True, slots=True)
class PhaseId:
    product: str
    component: str
    phase: str


@dataclass(frozen=True, order=True, slots=True)
class PhaseInstanceId:
    product: str
    component: str
    phase: str
    target: str

    @property
    def logical_phase(self) -> PhaseId:
        return PhaseId(self.product, self.component, self.phase)


@dataclass(frozen=True, slots=True)
class ComponentSpec:
    name: str
    product: str
    component: str
    default_target: str
    phases: tuple[str, ...]
    version_identity: str
    upstream_components: tuple[str, ...] = ()

    def phase_ids(self) -> tuple[PhaseId, ...]:
        return tuple(PhaseId(self.product, self.component, phase) for phase in self.phases)


def _component(
    name: str,
    product: str,
    component: str,
    default_target: str,
    phases: tuple[str, ...],
    version_identity: str,
    upstream_components: tuple[str, ...] = (),
) -> ComponentSpec:
    return ComponentSpec(
        name,
        product,
        component,
        default_target,
        phases,
        version_identity,
        upstream_components,
    )


COMPONENTS = tuple(sorted((
    _component("contract", "contract", "contract", "common", PHASE_ORDER, "contract"),
    *(
        _component(
            f"runtime-{component}",
            "runtime",
            component,
            component,
            PHASE_ORDER,
            "runtime-compatibility",
            ("contract",),
        )
        for component in RUNTIME_COMPONENTS
    ),
    _component(
        "runtime-aggregate",
        "runtime",
        "runtime-aggregate",
        "aggregate",
        ("metadata",),
        "runtime-release",
        tuple(f"runtime-{component}" for component in RUNTIME_COMPONENTS),
    ),
    _component("sdk-core", "sdk", "sdk-core", "common", PHASE_ORDER, "sdk", ("contract",)),
    _component("sdk-android", "sdk", "sdk-android", "android", PHASE_ORDER, "sdk", ("contract",)),
    _component("sdk-ios", "sdk", "sdk-ios", "ios", PHASE_ORDER, "sdk", ("contract",)),
    *(
        _component(
            f"binding-{language}",
            "sdk",
            language,
            "node" if language == "javascript" else "desktop",
            ("package", "validation", "metadata"),
            "sdk",
            ("contract", "runtime-node-js") if language == "javascript" else
            tuple(sorted(("contract", *(f"runtime-{target}" for target in NATIVE_TARGETS)))),
        )
        for language in BINDING_COMPONENTS
    ),
), key=lambda component: component.name))

COMPONENTS_BY_NAME = {component.name: component for component in COMPONENTS}
COMPONENTS_BY_IDENTITY = {
    (component.product, component.component): component for component in COMPONENTS
}
PHASE_IDS = tuple(sorted(phase for component in COMPONENTS for phase in component.phase_ids()))

PHASE_TARGET_OVERRIDES = {
    PhaseId("runtime", "jvm", "validation"): NATIVE_TARGETS,
    PhaseId("runtime", "node-js", "validation"):
        tuple(sorted((*NATIVE_TARGETS, "node-js-binding"))),
    PhaseId("runtime", "node-wasm", "validation"): NATIVE_TARGETS,
    PhaseId("sdk", "sdk-core", "validation"): SDK_FACADE_TARGETS,
    PhaseId("sdk", "sdk-ios", "validation"): ("ios-arm64", "ios-simulator-arm64"),
    **{
        PhaseId("sdk", language, "validation"): NATIVE_TARGETS
        for language in NATIVE_BINDINGS
    },
}

# Empty until an output contract proves that a concrete phase emits no product
# identity. Keeping this registry-owned prevents callers from omitting identity.
VERSIONLESS_PHASE_IDS: frozenset[PhaseId] = frozenset()


def component_for_phase(phase: PhaseId) -> ComponentSpec:
    component = COMPONENTS_BY_IDENTITY.get((phase.product, phase.component))
    if component is None or phase.phase not in component.phases:
        raise ValueError(f"Unknown product phase: {phase}")
    return component


def published_coordinate(product: str, component: str) -> str:
    try:
        return PUBLISHED_COORDINATES[(product, component)]
    except KeyError as error:
        raise ValueError(f"Unknown published product component: {product}/{component}") from error


def phase_targets(phase: PhaseId) -> tuple[str, ...]:
    component = component_for_phase(phase)
    return PHASE_TARGET_OVERRIDES.get(phase, (component.default_target,))


def phase_instances(phase: PhaseId) -> tuple[PhaseInstanceId, ...]:
    return tuple(
        PhaseInstanceId(phase.product, phase.component, phase.phase, target)
        for target in phase_targets(phase)
    )


PHASE_INSTANCE_IDS = tuple(sorted(
    instance for phase in PHASE_IDS for instance in phase_instances(phase)
))
NATIVE_BINARY_TOOLCHAIN_PROFILES = {
    PhaseInstanceId("runtime", target, "binary", target): target
    for target in NATIVE_TARGETS
}


def required_toolchain_profile(instance: PhaseInstanceId) -> str | None:
    if instance not in PHASE_INSTANCE_IDS:
        raise ValueError(f"Unknown product phase instance: {instance}")
    return NATIVE_BINARY_TOOLCHAIN_PROFILES.get(instance)


def phase_instance_dependencies(instance: PhaseInstanceId) -> tuple[PhaseInstanceId, ...]:
    phase = instance.logical_phase
    component = component_for_phase(phase)
    if instance.target not in phase_targets(phase):
        raise ValueError(f"Unsupported target for product phase: {instance}")

    dependencies: list[PhaseInstanceId] = []
    phase_index = component.phases.index(phase.phase)
    if phase_index:
        previous = PhaseId(component.product, component.component, component.phases[phase_index - 1])
        previous_targets = phase_targets(previous)
        if phase.phase == "metadata" and len(previous_targets) > 1:
            selected_targets = previous_targets
        elif instance.target in previous_targets:
            selected_targets = (instance.target,)
        else:
            selected_targets = (component.default_target,)
        dependencies.extend(
            PhaseInstanceId(previous.product, previous.component, previous.phase, target)
            for target in selected_targets
        )

    if phase.product == "runtime" and phase.component in RUNTIME_COMPONENTS and phase.phase == "binary":
        dependencies.append(PhaseInstanceId("contract", "contract", "metadata", "common"))
    elif phase == PhaseId("runtime", "runtime-aggregate", "metadata"):
        dependencies.extend(
            PhaseInstanceId("runtime", component_name, "metadata", component_name)
            for component_name in RUNTIME_COMPONENTS
        )
    elif phase.product == "sdk" and phase.component in {"sdk-core", "sdk-android", "sdk-ios"} and phase.phase == "binary":
        dependencies.append(PhaseInstanceId("contract", "contract", "metadata", "common"))
    elif phase == PhaseId("sdk", "sdk-core", "validation"):
        dependencies.append(PhaseInstanceId("contract", "contract", "metadata", "common"))
    elif (
        phase.product == "sdk"
        and phase.component in SDK_COMPATIBILITY_COMPONENTS
        and phase.phase == "package"
    ):
        dependencies.append(PhaseInstanceId("contract", "contract", "metadata", "common"))
        for target in NATIVE_TARGETS:
            dependencies.append(PhaseInstanceId("runtime", target, "metadata", target))
            if phase.component in NATIVE_BINDINGS:
                dependencies.extend((
                    PhaseInstanceId("runtime", target, "package", target),
                    PhaseInstanceId("runtime", target, "validation", target),
                ))
        dependencies.append(
            PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"),
        )
        if phase.component == "javascript":
            dependencies.append(PhaseInstanceId("runtime", "node-js", "package", "node-js"))
    elif phase.product == "sdk" and phase.component in NATIVE_BINDINGS and phase.phase == "validation":
        dependencies.append(PhaseInstanceId("runtime", instance.target, "validation", instance.target))
    elif phase == PhaseId("sdk", "javascript", "validation"):
        dependencies.append(PhaseInstanceId("runtime", "node-js", "validation", "node-js-binding"))

    if (
        phase.product == "runtime"
        and phase.component in RUNTIME_ADAPTERS
        and phase.phase == "validation"
        and instance.target in NATIVE_TARGETS
    ):
        dependencies.append(PhaseInstanceId("runtime", instance.target, "package", instance.target))
    return tuple(sorted(set(dependencies)))


def required_contract_components(instance: PhaseInstanceId) -> tuple[str, ...]:
    """Return the exact signed Contract components consumed by this phase."""
    phase = instance.logical_phase
    if instance.target not in phase_targets(phase):
        raise ValueError(f"Unsupported target for product phase: {instance}")
    if phase.product == "runtime" and phase.component in RUNTIME_COMPONENTS and phase.phase == "binary":
        components = (phase.component,)
    elif phase == PhaseId("sdk", "sdk-core", "binary"):
        components = ("common",)
    elif phase == PhaseId("sdk", "sdk-core", "validation"):
        components = (SDK_FACADE_CONTRACT_COMPONENTS[instance.target],)
    elif phase == PhaseId("sdk", "sdk-android", "binary"):
        components = ("android",)
    elif phase == PhaseId("sdk", "sdk-ios", "binary"):
        components = ("ios-arm64", "ios-simulator-arm64")
    elif phase == PhaseId("sdk", "sdk-core", "package"):
        components = ("common",)
    elif phase == PhaseId("sdk", "sdk-android", "package"):
        components = ("android",)
    elif phase == PhaseId("sdk", "sdk-ios", "package"):
        components = ("ios-arm64", "ios-simulator-arm64")
    elif phase.product == "sdk" and phase.component in NATIVE_BINDINGS and phase.phase == "package":
        components = ("common",)
    elif phase == PhaseId("sdk", "javascript", "package"):
        components = ("node-js",)
    else:
        components = ()
    if any(component not in CONTRACT_COMPONENTS for component in components):
        raise ValueError(f"Unknown Contract component for product phase: {instance}")
    return tuple(sorted(components))


def phase_dependencies(phase: PhaseId) -> tuple[PhaseId, ...]:
    return tuple(sorted({
        dependency.logical_phase
        for instance in phase_instances(phase)
        for dependency in phase_instance_dependencies(instance)
    }))


def validate_registry() -> None:
    if PHASE_ORDER != tuple(phase for phase in PHASE_ORDER if phase in RECEIPT_PHASES):
        raise ValueError("Registry phase order disagrees with receipt schema")
    if len(COMPONENTS) != 19 or len(PHASE_IDS) != 67 or len(PHASE_INSTANCE_IDS) != 111:
        raise ValueError("Registry must contain 19 components, 67 phases, and 111 instances")
    if tuple(component.name for component in COMPONENTS) != tuple(sorted(COMPONENTS_BY_NAME)):
        raise ValueError("Product component names must be sorted and unique")
    if len(COMPONENTS_BY_IDENTITY) != len(COMPONENTS):
        raise ValueError("Product component identities must be unique")
    if len(PHASE_IDS) != len(set(PHASE_IDS)) or len(PHASE_INSTANCE_IDS) != len(set(PHASE_INSTANCE_IDS)):
        raise ValueError("Product phase identities must be unique")
    if set(NATIVE_BINARY_TOOLCHAIN_PROFILES.values()) != set(NATIVE_TARGETS) or any(
        instance not in PHASE_INSTANCE_IDS
        or instance.product != "runtime"
        or instance.component != instance.target
        or instance.phase != "binary"
        or profile != instance.target
        for instance, profile in NATIVE_BINARY_TOOLCHAIN_PROFILES.items()
    ):
        raise ValueError("Native binary toolchain profile ownership is invalid")
    if not VERSIONLESS_PHASE_IDS.issubset(PHASE_IDS):
        raise ValueError("Versionless phase identities must exist in the product registry")
    for component in COMPONENTS:
        if component.product not in PRODUCTS:
            raise ValueError(f"Unsupported product for {component.name}")
        if component.phases != tuple(phase for phase in PHASE_ORDER if phase in component.phases):
            raise ValueError(f"Phases for {component.name} are not ordered")
        if component.version_identity not in VERSION_IDENTITIES:
            raise ValueError(f"Unsupported version identity for {component.name}")
        if component.upstream_components != tuple(sorted(component.upstream_components)):
            raise ValueError(f"Upstream components for {component.name} must be sorted")
        if any(upstream not in COMPONENTS_BY_NAME for upstream in component.upstream_components):
            raise ValueError(f"Unknown upstream component for {component.name}")
    for targets in PHASE_TARGET_OVERRIDES.values():
        if not targets or targets != tuple(sorted(set(targets))):
            raise ValueError("Phase targets must be sorted and unique")

    visiting: set[PhaseInstanceId] = set()
    visited: set[PhaseInstanceId] = set()

    def visit(instance: PhaseInstanceId) -> None:
        if instance in visiting:
            raise ValueError("Product phase-instance dependencies contain a cycle")
        if instance in visited:
            return
        visiting.add(instance)
        for dependency in phase_instance_dependencies(instance):
            if dependency not in PHASE_INSTANCE_IDS:
                raise ValueError(f"Unknown phase-instance dependency: {dependency}")
            visit(dependency)
        visiting.remove(instance)
        visited.add(instance)

    for instance in PHASE_INSTANCE_IDS:
        contract_dependency = PhaseInstanceId("contract", "contract", "metadata", "common")
        has_contract_dependency = contract_dependency in phase_instance_dependencies(instance)
        if has_contract_dependency != bool(required_contract_components(instance)):
            raise ValueError(f"Contract component ownership is incomplete: {instance}")
        visit(instance)


validate_registry()
