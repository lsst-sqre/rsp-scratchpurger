"""Exceptions for the purger."""

from safir.slack.blockkit import SlackException


class PlanNotReadyError(SlackException):
    """An operation needing a Plan was requested, but no Plan is ready."""


class PolicyNotFoundError(SlackException):
    """No Policy matching the given directory was found."""
