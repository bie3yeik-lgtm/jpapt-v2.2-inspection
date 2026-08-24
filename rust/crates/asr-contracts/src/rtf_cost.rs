use serde::{Deserialize, Serialize};

use crate::{ContractError, Result};

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct RtfCostPolicy {
    pub schema_version: u32,
    pub targets: Vec<RtfCostTarget>,
    pub batch_sizes: Vec<u32>,
    pub repeat: RtfCostBounds,
    pub sample_count: RtfCostBounds,
    pub target_total_sec: RtfCostBounds,
    pub max_duration_sec: RtfCostBounds,
    pub modes: Vec<String>,
    pub remote_timeout: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct RtfCostTarget {
    pub provider: String,
    pub gpus: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct RtfCostBounds {
    pub min: u32,
    pub max: u32,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct RtfCostPlan {
    pub schema_version: u32,
    pub provider: String,
    pub gpu: String,
    pub batch_size: u32,
    pub repeat: u32,
    pub sample_count: u32,
    pub target_total_sec: u32,
    pub max_duration_sec: u32,
    pub mode: String,
    pub remote_timeout: String,
    pub early_stop_on_failure: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RtfCostRequest {
    pub provider: String,
    pub gpu: String,
    pub batch_size: u32,
    pub repeat: u32,
    pub sample_count: u32,
    pub target_total_sec: u32,
    pub max_duration_sec: u32,
    pub mode: String,
    pub allow_expensive_matrix: bool,
}

pub fn validate_rtf_cost_plan(
    request: &RtfCostRequest,
    policy: &RtfCostPolicy,
) -> Result<RtfCostPlan> {
    if policy.schema_version != 1 {
        return Err(ContractError::validation(format!(
            "unsupported RTF cost policy schema_version: {}",
            policy.schema_version
        )));
    }
    let valid_target = policy.targets.iter().any(|target| {
        target.provider == request.provider
            && (target.gpus.iter().any(|gpu| gpu == &request.gpu)
                || target
                    .gpus
                    .iter()
                    .any(|gpu| gpu == "*" && !request.gpu.is_empty()))
    });
    if !valid_target {
        return Err(ContractError::validation(format!(
            "unsupported provider/GPU in external policy: {}/{}",
            request.provider, request.gpu
        )));
    }
    if policy.batch_sizes.is_empty() {
        return Err(ContractError::validation(
            "external policy must define at least one batch size",
        ));
    }
    if !policy.batch_sizes.contains(&request.batch_size) {
        return Err(ContractError::validation(format!(
            "batch_size is not enabled by external policy: {}",
            request.batch_size
        )));
    }
    check_bounds("repeat", request.repeat, &policy.repeat)?;
    check_bounds("sample_count", request.sample_count, &policy.sample_count)?;
    check_bounds(
        "target_total_sec",
        request.target_total_sec,
        &policy.target_total_sec,
    )?;
    check_bounds(
        "max_duration_sec",
        request.max_duration_sec,
        &policy.max_duration_sec,
    )?;
    if !policy.modes.iter().any(|mode| mode == &request.mode) {
        return Err(ContractError::validation(format!(
            "mode is not enabled by external policy: {}",
            request.mode
        )));
    }
    if request.mode == "full-matrix" && !request.allow_expensive_matrix {
        return Err(ContractError::validation(
            "full-matrix requires explicit expensive-matrix approval",
        ));
    }
    if policy.remote_timeout.trim().is_empty() {
        return Err(ContractError::validation(
            "external policy remote_timeout must not be empty",
        ));
    }
    Ok(RtfCostPlan {
        schema_version: 1,
        provider: request.provider.clone(),
        gpu: request.gpu.clone(),
        batch_size: request.batch_size,
        repeat: request.repeat,
        sample_count: request.sample_count,
        target_total_sec: request.target_total_sec,
        max_duration_sec: request.max_duration_sec,
        mode: request.mode.clone(),
        remote_timeout: policy.remote_timeout.clone(),
        early_stop_on_failure: request.mode == "guarded",
    })
}

fn check_bounds(name: &str, value: u32, bounds: &RtfCostBounds) -> Result<()> {
    if bounds.min == 0 || bounds.min > bounds.max || !(bounds.min..=bounds.max).contains(&value) {
        return Err(ContractError::validation(format!(
            "{name} must be between {} and {} according to external policy",
            bounds.min, bounds.max
        )));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{
        RtfCostBounds, RtfCostPolicy, RtfCostRequest, RtfCostTarget, validate_rtf_cost_plan,
    };

    fn policy() -> RtfCostPolicy {
        RtfCostPolicy {
            schema_version: 1,
            targets: vec![
                RtfCostTarget {
                    provider: "hf".into(),
                    gpus: vec!["t4".into(), "l4".into()],
                },
                RtfCostTarget {
                    provider: "runpod".into(),
                    gpus: vec!["a5000".into(), "l4".into(), "a4000".into(), "a4500".into()],
                },
                RtfCostTarget {
                    provider: "vast".into(),
                    gpus: vec!["*".into()],
                },
            ],
            batch_sizes: vec![1, 8, 32],
            repeat: RtfCostBounds { min: 1, max: 3 },
            sample_count: RtfCostBounds { min: 1, max: 50 },
            target_total_sec: RtfCostBounds { min: 1, max: 5400 },
            max_duration_sec: RtfCostBounds { min: 1, max: 600 },
            modes: vec!["guarded".into(), "full-matrix".into()],
            remote_timeout: "2h".into(),
        }
    }

    fn request(provider: &str, gpu: &str, mode: &str) -> RtfCostRequest {
        RtfCostRequest {
            provider: provider.into(),
            gpu: gpu.into(),
            batch_size: 1,
            repeat: 3,
            sample_count: 50,
            target_total_sec: 5400,
            max_duration_sec: 600,
            mode: mode.into(),
            allow_expensive_matrix: mode == "full-matrix",
        }
    }

    #[test]
    fn guarded_plan_uses_external_policy() {
        let plan = validate_rtf_cost_plan(&request("hf", "t4", "guarded"), &policy()).unwrap();
        assert!(plan.early_stop_on_failure);
        assert_eq!(plan.remote_timeout, "2h");
    }

    #[test]
    fn policy_controls_targets_and_batch_sizes() {
        assert!(
            validate_rtf_cost_plan(&request("runpod", "rtx4090", "guarded"), &policy()).is_err()
        );
        let mut request = request("hf", "t4", "guarded");
        request.batch_size = 4;
        assert!(validate_rtf_cost_plan(&request, &policy()).is_err());
    }

    #[test]
    fn full_matrix_requires_explicit_approval() {
        let mut request = request("runpod", "a5000", "full-matrix");
        request.allow_expensive_matrix = false;
        assert!(validate_rtf_cost_plan(&request, &policy()).is_err());
        request.allow_expensive_matrix = true;
        assert!(validate_rtf_cost_plan(&request, &policy()).is_ok());
    }

    #[test]
    fn runpod_phase_one_gpu_targets_are_accepted() {
        for gpu in ["l4", "a4000", "a4500"] {
            let plan = validate_rtf_cost_plan(&super::RtfCostRequest {
                provider: "runpod".into(),
                gpu: gpu.into(),
                batch_size: 1,
                repeat: 3,
                sample_count: 50,
                target_total_sec: 5400,
                max_duration_sec: 600,
                mode: "guarded".into(),
                allow_expensive_matrix: false,
            })
            .expect("new RunPod GPU target must be accepted by the cost policy");
            assert_eq!(plan.gpu, gpu);
        }
    }
}
