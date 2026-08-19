#!/usr/bin/env bash

# Shared canonical Hugging Face transport identity helpers.
# Callers own error reporting; these functions print only the normalized value.

hf_normalize_bucket_id() {
    local value="$1" namespace name
    value="${value#hf://buckets/}"
    value="${value%/}"
    [[ "$value" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || return 1
    namespace="${value%%/*}"
    name="${value#*/}"
    [[ "$namespace" != "." && "$namespace" != ".." && "$name" != "." && "$name" != ".." ]] || return 1
    printf '%s\n' "$value"
}

hf_normalize_model_repo_id() {
    local value="$1" namespace name
    value="${value#hf://models/}"
    value="${value#hf://}"
    value="${value%/}"
    [[ "$value" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || return 1
    namespace="${value%%/*}"
    name="${value#*/}"
    [[ "$namespace" != "." && "$namespace" != ".." && "$name" != "." && "$name" != ".." ]] || return 1
    printf '%s\n' "$value"
}
