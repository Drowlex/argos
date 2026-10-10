#!/bin/bash

# This scripts terminates all in-progress dagster runs using graphql API.
# It is used before shutting down dagster to prevent hanging jobs.

# bash shell Initialize empty RUN_IDS array
# RUN_IDS=()

DOMAIN=http://local.com:13000

# Get all in-progress runs' ids, value can be null if no runs are in-progress. Check runsOrError object.
# RUN_IDS=$(curl -s -X POST -H "Content-Type: application/json" -d '{"query": "query FilteredRunsQuery { runsOrError(filter: { statuses:[STARTING, STARTED, CANCELING, QUEUED, SUCCESS] }) { __typename ... on Runs { results { runId } } } }"}' $DOMAIN/graphql | jq -r 'try .data.runsOrError.results[].runId')
RUN_IDS=$(curl -s -X POST -H "Content-Type: application/json" -d '{"query": "query FilteredRunsQuery { runsOrError(filter: { statuses:[SUCCESS, FAILURE, CANCELED] }) { __typename ... on Runs { results { runId } } } }"}' $DOMAIN/graphql | jq -r 'try .data.runsOrError.results[].runId')
# RUN_IDS=$(curl -s -X POST -H "Content-Type: application/json" -d '{"query": "query FilteredRunsQuery { runsOrError(filter: { statuses:[SUCCESS, FAILURE, CANCELED, CANCELING] }) { __typename ... on Runs { results { runId } } } }"}' $DOMAIN/graphql | jq -r 'try .data.runsOrError.results[].runId')

# Terminate all in-progress runs.
if [ -z "$RUN_IDS" ]; then
    echo "No in-progress dagster runs found."
else
    # Terminate all in-progress runs
    for RUN_ID in $RUN_IDS; do
        echo "Terminating run $RUN_ID"
        curl -s -X POST -H "Content-Type: application/json" --data-raw '{"operationName":"Delete","variables":{"runId": "'$RUN_ID'"},"query":"mutation Delete($runId: String!) { deletePipelineRun(runId: $runId) { ... on UnauthorizedError { message __typename } ... on RunNotFoundError { message __typename } ...PythonErrorFragment __typename } } fragment PythonErrorFragment on PythonError { message stack errorChain { ...PythonErrorChain __typename } __typename } fragment PythonErrorChain on ErrorChainLink { isExplicitLink error { message stack __typename } __typename }"}' $DOMAIN/graphql | jq -r 'try .data.terminateRun.run.runId'
    done
fi

# Example crontab
# 0 8 * * * /bin/bash /home/ubuntu/user1/erase-logs.sh > /dev/null 2>&1