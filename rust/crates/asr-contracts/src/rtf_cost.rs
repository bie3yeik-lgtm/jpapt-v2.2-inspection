use serde::Serialize;

use crate::{ContractError, Result};

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
    pub remote_timeout: &'static str,
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

pub fn validate_rtf_cost_plan(request: &RtfCostRequest) -> Result<RtfCostPlan> {
    let provider = request.provider.as_str();
    let gpu = request.gpu.as_str();
    let batch_size = request.batch_size;
    let repeat = request.repeat;
    let sample_count = request.sample_count;
    let target_total_sec = request.target_total_sec;
    let max_duration_sec = request.max_duration_sec;
    let mode = request.mode.as_str();
    let valid_gpu = matches!(
        (provider, gpu),
        ("hf", "t4" | "l4") | ("runpod", "a5000" | "a40" | "l4" | "rtx3090" | "rtx4090")
    );
    if !valid_gpu {
        return Err(ContractError::validation(format!(
            "unsupported provider/GPU: {provider}/{gpu}"
        )));
    }
    if !matches!(batch_size, 1 | 8 | 32) {
        return Err(ContractError::validation("batch_size must be 1, 8, or 32"));
    }
    if !(1..=3).contains(&repeat) {
        return Err(ContractError::validation("repeat must be between 1 and 3"));
    }
    if !(1..=50).contains(&sample_count) {
        return Err(ContractError::validation(
            "sample_count must be between 1 and 50",
        ));
    }
    if !(1..=5400).contains(&target_total_sec) {
        return Err(ContractError::validation(
            "target_total_sec must be between 1 and 5400",
        ));
    }
    if !(1..=600).contains(&max_duration_sec) {
        return Err(ContractError::validation(
            "max_duration_sec must be between 1 and 600",
        ));
    }
    if !matches!(mode, "guarded" | "full-matrix") {
        return Err(ContractError::validation(
            "mode must be guarded or full-matrix",
        ));
    }
    if mode == "full-matrix" && !request.allow_expensive_matrix {
        return Err(ContractError::validation(
            "full-matrix requires explicit expensive-matrix approval",
        ));
    }
    Ok(RtfCostPlan {
        schema_version: 1,
        provider: request.provider.clone(),
        gpu: request.gpu.clone(),
        batch_size,
        repeat,
        sample_count,
        target_total_sec,
        max_duration_sec,
        mode: request.mode.clone(),
        remote_timeout: "2h",
        early_stop_on_failure: mode == "guarded",
    })
}

#[cfg(test)]
mod tests {
    use super::validate_rtf_cost_plan;

    #[test]
    fn guarded_plan_is_accepted() {
        let plan = validate_rtf_cost_plan(&super::RtfCostRequest {
            provider: "hf".into(),
            gpu: "t4".into(),
            batch_size: 1,
            repeat: 3,
            sample_count: 50,
            target_total_sec: 5400,
            max_duration_sec: 600,
            mode: "guarded".into(),
            allow_expensive_matrix: false,
        })
        .unwrap();
        assert!(plan.early_stop_on_failure);
    }

    #[test]
    fn full_matrix_requires_explicit_approval() {
        assert!(
            validate_rtf_cost_plan(&super::RtfCostRequest {
                provider: "runpod".into(),
                gpu: "a5000".into(),
                batch_size: 8,
                repeat: 3,
                sample_count: 50,
                target_total_sec: 5400,
                max_duration_sec: 600,
                mode: "full-matrix".into(),
                allow_expensive_matrix: false
            })
            .is_err()
        );
        assert!(
            validate_rtf_cost_plan(&super::RtfCostRequest {
                provider: "runpod".into(),
                gpu: "a5000".into(),
                batch_size: 8,
                repeat: 3,
                sample_count: 50,
                target_total_sec: 5400,
                max_duration_sec: 600,
                mode: "full-matrix".into(),
                allow_expensive_matrix: true
            })
            .is_ok()
        );
    }
}
