class TdtDecoderNotImplemented(NotImplementedError):
    """Raised until the TDT deployment decoder contract is implemented."""


def decode_tdt(*args, **kwargs):
    raise TdtDecoderNotImplemented(
        "TDT deployment decoding is intentionally deferred until the CTC "
        "path has stable export and parity results."
    )
