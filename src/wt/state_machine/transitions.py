from __future__ import annotations

LIFECYCLE_TRANSITIONS = {
    "ABSENT": {
        "CreateRequested": "CREATING",
    },
    "CREATING": {
        "CreateSucceeded": "READY",
        "CreateFailed": "BROKEN",
    },
    "READY": {
        "PathMissingDetected": "BROKEN",
        "RemoveRequested": "REMOVING",
    },
    "BROKEN": {
        "RepairSucceeded": "READY",
        "RemoveRequested": "REMOVING",
    },
    "REMOVING": {
        "RemoveSucceeded": "ABSENT",
        "RemoveFailed": "BROKEN",
    },
}

BOOTSTRAP_TRANSITIONS = {
    "UNBOOTSTRAPPED": {
        "BootstrapRequested": "BOOTSTRAPPING",
    },
    "BOOTSTRAPPING": {
        "BootstrapSucceeded": "BOOTSTRAPPED",
        "BootstrapFailed": "BOOTSTRAP_ERROR",
    },
    "BOOTSTRAPPED": {
        "ConfigChangedDetected": "UNBOOTSTRAPPED",
        "BootstrapRequested": "BOOTSTRAPPING",
    },
    "BOOTSTRAP_ERROR": {
        "BootstrapRequested": "BOOTSTRAPPING",
    },
}

AGENT_TRANSITIONS = {
    "DETACHED": {
        "AttachRequested": "ATTACHING",
    },
    "ATTACHING": {
        "AttachSucceeded": "ATTACHED",
        "AttachFailed": "ATTACH_ERROR",
    },
    "ATTACHED": {
        "DetachRequested": "DETACHED",
    },
    "ATTACH_ERROR": {
        "AttachRequested": "ATTACHING",
    },
}

RUNTIME_TRANSITIONS = {
    "STOPPED": {
        "StartRequested": "STARTING",
    },
    "STARTING": {
        "StartSucceeded": "RUNNING",
        "StartFailed": "CRASHED",
    },
    "RUNNING": {
        "StopRequested": "STOPPING",
        "CrashDetected": "CRASHED",
    },
    "STOPPING": {
        "StopSucceeded": "STOPPED",
        "StopFailed": "CRASHED",
    },
    "CRASHED": {
        "StartRequested": "STARTING",
        "StopRequested": "STOPPING",
    },
}
