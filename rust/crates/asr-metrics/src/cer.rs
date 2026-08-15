use unicode_normalization::UnicodeNormalization;
use crate::edit_distance::edit_distance;

pub fn normalize_text(text: &str) -> String {
    text.nfkc().collect::<String>().split_whitespace().collect::<Vec<_>>().join(" ")
}

pub fn character_error_rate(reference: &str, hypothesis: &str) -> f64 {
    let r: Vec<char> = normalize_text(reference).chars().collect();
    let h: Vec<char> = normalize_text(hypothesis).chars().collect();
    if r.is_empty() { return if h.is_empty() { 0.0 } else { 1.0 }; }
    edit_distance(&r, &h) as f64 / r.len() as f64
}
