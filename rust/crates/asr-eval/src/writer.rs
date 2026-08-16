use crate::Result;
use std::{
    fs::{self, File},
    io::{BufWriter, Write},
    path::Path,
};
pub fn ensure_dir(path: &Path) -> Result<()> {
    fs::create_dir_all(path)?;
    Ok(())
}
pub fn write_json(path: &Path, value: &serde_json::Value) -> Result<()> {
    fs::write(path, serde_json::to_vec_pretty(value)?)?;
    Ok(())
}
pub fn write_jsonl(path: &Path, values: &[serde_json::Value]) -> Result<()> {
    let mut w = BufWriter::new(File::create(path)?);
    for value in values {
        serde_json::to_writer(&mut w, value)?;
        w.write_all(b"\n")?;
    }
    w.flush()?;
    Ok(())
}
