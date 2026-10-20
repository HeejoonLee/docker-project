#!/bin/sh
# Create the namespace and Stonepedia's search attributes. Safe to run on every start.
set -eu
A=temporal:7233
NS=default
until temporal operator cluster health --address $A >/dev/null 2>&1; do
  echo "waiting for Temporal..."; sleep 2
done
temporal operator namespace describe -n $NS --address $A >/dev/null 2>&1 \
  || temporal operator namespace create -n $NS --retention 365d --address $A
for attr in Bundle ProposalState; do
  until temporal operator search-attribute list -n $NS --address $A | grep -q "^ *$attr "; do
    temporal operator search-attribute create -n $NS --address $A --name $attr --type Keyword || sleep 2
  done
done
echo "Temporal namespace '$NS' ready"
