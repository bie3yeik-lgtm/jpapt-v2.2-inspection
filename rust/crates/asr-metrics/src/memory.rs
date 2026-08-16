pub fn current_process_memory_mb() -> Option<f64> {
    let pid = sysinfo::get_current_pid().ok()?;
    let mut system = sysinfo::System::new();
    system.refresh_processes(sysinfo::ProcessesToUpdate::Some(&[pid]), true);
    system
        .process(pid)
        .map(|p| p.memory() as f64 / (1024.0 * 1024.0))
}
