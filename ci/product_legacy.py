from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

if __package__:
    from .legacy_lanes import LANES
    from .products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PHASE_INSTANCE_IDS, PhaseInstanceId
else:
    from legacy_lanes import LANES
    from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PHASE_INSTANCE_IDS, PhaseInstanceId


_ALL_INSTANCES = frozenset(PHASE_INSTANCE_IDS)
_ACTION_ORDER = {action: index for index, action in enumerate(("build", "test", "metadata"))}
_LANE_ORDER = {lane: index for index, lane in enumerate(LANES)}
_DESKTOP_LANES = tuple(f"desktop-{target}" for target in NATIVE_TARGETS)


@dataclass(frozen=True, slots=True)
class LegacyLaneProjection:
    actions: tuple[tuple[str, str], ...]
    full: bool
    fallback_instances: tuple[PhaseInstanceId, ...]


def project_legacy_lanes(unresolved: Iterable[PhaseInstanceId]) -> LegacyLaneProjection:
    if isinstance(unresolved, (str, bytes)):
        raise ValueError("Unresolved product phases must be an iterable of phase instances")
    instances = tuple(unresolved)
    if any(not isinstance(instance, PhaseInstanceId) or instance not in _ALL_INSTANCES for instance in instances):
        raise ValueError("Unresolved product phases contain an unknown phase instance")
    if len(instances) != len(set(instances)):
        raise ValueError("Unresolved product phases must be unique")

    selected = set(instances)

    def predecessor_selected(instance: PhaseInstanceId) -> bool:
        return any(
            candidate.product == instance.product
            and candidate.component == instance.component
            and candidate.phase != "metadata"
            for candidate in selected
        )

    actions: set[tuple[str, str]] = set()
    fallback: list[PhaseInstanceId] = []
    for instance in instances:
        product, component, phase, target = (
            instance.product, instance.component, instance.phase, instance.target
        )
        if product == "contract":
            actions.add(("contracts", {"binary": "build", "package": "build", "validation": "test", "metadata": "metadata"}[phase]))
        elif product == "runtime" and component in NATIVE_TARGETS:
            if phase == "metadata":
                if not predecessor_selected(instance):
                    fallback.append(instance)
            else:
                actions.add((f"desktop-{component}", "test" if phase == "validation" else "build"))
        elif product == "runtime" and component == "jvm":
            if phase == "metadata":
                if not predecessor_selected(instance):
                    fallback.append(instance)
            elif phase == "validation":
                actions.add((f"desktop-{target}", "test"))
            else:
                actions.add(("portable", "build"))
        elif product == "runtime" and component == "node-js":
            if phase == "metadata":
                if not predecessor_selected(instance):
                    fallback.append(instance)
            elif phase == "validation":
                actions.add(("node-js", "test") if target == "node-js-binding" else (f"desktop-{target}", "test"))
            else:
                actions.add(("node-js", "build"))
        elif product == "runtime" and component == "node-wasm":
            if phase == "metadata":
                if not predecessor_selected(instance):
                    fallback.append(instance)
            elif phase == "validation":
                actions.add((f"desktop-{target}", "test"))
            else:
                actions.add(("portable", "build"))
        elif product == "runtime" and component == "runtime-aggregate":
            if not any(
                candidate.product == "runtime" and candidate.component != "runtime-aggregate"
                for candidate in selected
            ):
                fallback.append(instance)
        elif product == "sdk" and component == "sdk-android":
            actions.add(("android", {"binary": "build", "package": "build", "validation": "test", "metadata": "metadata"}[phase]))
        elif product == "sdk" and component == "sdk-ios":
            if phase == "binary":
                actions.update((lane, "build") for lane in (
                    "ios-rust-device", "ios-rust-simulator",
                    "ios-framework-device", "ios-framework-simulator",
                ))
            elif phase == "package":
                actions.add(("ios-package", "build"))
            elif phase == "validation" and target == "ios-arm64":
                actions.update((lane, action) for lane, action in (
                    ("ios-native-tests", "test"), ("ios-swift-tests", "test"),
                    ("consumer-ios-device", "build"),
                ))
            elif phase == "validation" and target == "ios-simulator-arm64":
                actions.update((lane, action) for lane, action in (
                    ("ios-native-tests", "test"), ("ios-kotlin-tests", "test"),
                    ("ios-swift-build", "test"), ("ios-swift-tests", "test"),
                    ("consumer-ios-simulator", "build"),
                ))
            elif phase == "metadata":
                actions.update((("ios-package", "metadata"), ("ios-privacy-metrics", "metadata")))
            else:
                raise ValueError(f"Unsupported legacy iOS projection: {instance}")
        elif product == "sdk" and component == "sdk-core":
            fallback.append(instance)
        elif product == "sdk" and component in NATIVE_BINDINGS:
            if phase == "metadata":
                if not predecessor_selected(instance):
                    fallback.append(instance)
            else:
                actions.update((lane, action) for lane in _DESKTOP_LANES for action in ("build", "test"))
        elif product == "sdk" and component == "javascript":
            if phase == "metadata":
                if not predecessor_selected(instance):
                    fallback.append(instance)
            else:
                actions.add(("node-js", "build" if phase == "package" else "test"))
        else:
            raise ValueError(f"Product phase has no legacy projection: {instance}")

    ordered_actions = tuple(sorted(
        actions,
        key=lambda value: (_LANE_ORDER[value[0]], _ACTION_ORDER[value[1]]),
    ))
    return LegacyLaneProjection(ordered_actions, bool(fallback), tuple(sorted(fallback)))
