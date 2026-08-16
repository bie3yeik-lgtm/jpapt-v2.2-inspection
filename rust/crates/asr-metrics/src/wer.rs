use crate::{cer::normalize_text, edit_distance::edit_distance};

pub fn word_error_rate(reference: &str, hypothesis: &str) -> f64 {
    let rn = normalize_text(reference);
    let hn = normalize_text(hypothesis);
    let r: Vec<&str> = rn.split_whitespace().collect();
    let h: Vec<&str> = hn.split_whitespace().collect();
    if r.is_empty() {
        return if h.is_empty() { 0.0 } else { 1.0 };
    }
    edit_distance(&r, &h) as f64 / r.len() as f64
}
