"""Custom Temporal search attributes. Registered by the compose init job and `make dev`."""

from temporalio.common import SearchAttributeKey

BUNDLE = SearchAttributeKey.for_keyword("Bundle")
PROPOSAL_STATE = SearchAttributeKey.for_keyword("ProposalState")

ALL = [BUNDLE, PROPOSAL_STATE]
