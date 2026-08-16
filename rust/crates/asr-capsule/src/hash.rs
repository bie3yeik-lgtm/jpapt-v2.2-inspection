use std::{fs::File, io::Read, path::Path};

use anyhow::Result;
use sha2::{Digest, Sha256};

pub fn sha256_file(path: impl AsRef<Path>) -> Result<String> {
    let mut file = File::open(path)?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let read = file.read(&mut buffer)?;
        if read == 0 { break; }
        digest.update(&buffer[..read]);
    }
    Ok(format!("{digest:x}"))
}
