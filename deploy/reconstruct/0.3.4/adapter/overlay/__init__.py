"""A23 overlay subtree: the GroupCoordinator wiring piece (v2, five modes).

install_overlay(parallel_state_module) is the single entry; see
a23_group_overlay.install_overlay for the mount/wrap semantics and
a23_forms for the three switchable replacement forms.
"""
from .a23_group_overlay import install_overlay

__all__ = ["install_overlay"]
