from collections import namedtuple

import block
import transaction
import opcodes

class ParamsPreset(object):
    """Chainparams preset.

    Attributes:
        - name (str): Identifier (e.g. 'Bitcoin').
        - tx_fields (list): Transaction format. List of 4-tuples in the form:
            (attribute_name, fmt, num_bytes, default), where:
                - attribute_name (str): Name of the tx attribute.
                - fmt (str): struct format string, or for special cases,
                    'inputs', 'outputs', or 'bytes'.
                - num_bytes (int): Number of bytes for deserializer to read,
                - default: Default value.
        - block_header_fields (list): Block header format. Same form as tx_fields.
            If not specified, the 80-byte Bitcoin block header format is used.
        - block_fields (list): Block (excluding header) format.
        - opcode_overrides (list): List of 3-tuples in the form:
            (value, name, func), where:
                - value (int): Opcode value.
                - name (str): Opcode name.
                - func: Function that takes stack data and executes the opcode.
                    This function should take the arguments (stack, txTo, inIdx, flags, err_raiser) and
                    return (stack, opcode, log_message).

    """
    def __init__(self, **kwargs):
        self.name = ''
        self.tx_fields = []
        self.block_header_fields = list(_bitcoin_header_fields)
        self.block_fields = list(_bitcoin_block_fields)
        self.opcode_overrides = list(_bitcoin_opcode_overrides)

        for k, v in kwargs.items():
            setattr(self, k, v)

_bitcoin_header_fields = [
    ('nVersion', b'<i', 4, 1),
    ('hashPrevBlock', 'bytes', 32, b'\x00'*32),
    ('hashMerkleRoot', 'bytes', 32, b'\x00'*32),
    ('nTime', b'<I', 4, 0),
    ('nBits', b'<I', 4, 0),
    ('nNonce', b'<I', 4, 0)
]

_bitcoin_block_fields = [
    ('vtx', 'vectortx', None, None)
]

_bitcoin_opcode_overrides = []

BitcoinPreset = ParamsPreset(
        name='Bitcoin',
        tx_fields=[('nVersion', b'<i', 4, 1),
            ('vin', 'inputs', None, None),
            ('vout', 'outputs', None, None),
            ('nLockTime', b'<I', 4, 0)]
)

ClamsPreset = ParamsPreset(
        name='Clams',
        tx_fields=[('nVersion', b'<i', 4, 1),
            ('Timestamp', b'<i', 4, 0),
            ('vin', 'inputs', None, None),
            ('vout', 'outputs', None, None),
            ('nLockTime', b'<I', 4, 0),
            ('ClamSpeech', 'bytes', None, b'')],
        block_fields = list(_bitcoin_block_fields) + [('blockSig', 'bytes', None, None)],
        opcode_overrides=[(0xb0, 'OP_CHECKLOCKTIMEVERIFY', opcodes.clams_checklocktimeverify)]
)

FreicoinPreset = ParamsPreset(
        name='Freicoin',
        tx_fields=[('nVersion', b'<i', 4, 1),
            ('vin', 'inputs', None, None),
            ('vout', 'outputs', None, None),
            ('nLockTime', b'<I', 4, 0),
            ('RefHeight', b'<i', 4, 0)]
)

PeercoinPreset = ParamsPreset(
        name='Peercoin',
        tx_fields=[('nVersion', b'<i', 4, 1),
            ('Timestamp', b'<i', 4, 0),
            ('vin', 'inputs', None, None),
            ('vout', 'outputs', None, None),
            ('nLockTime', b'<I', 4, 0)]
)

presets_list = [
        BitcoinPreset,
        ClamsPreset,
        FreicoinPreset,
        PeercoinPreset
]

presets = dict((i.name, i) for i in presets_list)


def get_tx_fields():
    return transaction.transaction_fields

def set_tx_fields(fields):
    """Set the format of transactions.

    This affects all Transaction instances created afterward.
    """
    transaction.transaction_fields = list(fields)

def get_block_header_fields():
    return block.block_header_fields

def set_block_header_fields(fields):
    """Set the format of block headers.

    This affects all BlockHeader instances created afterward.
    """
    block.block_header_fields = list(fields)

def get_block_fields():
    return block.block_fields

def set_block_fields(fields):
    """Set the format of blocks (excluding their headers).

    This affects all Block instances created afterward.
    """
    block.block_fields = list(fields)

def get_opcode_overrides():
    return opcodes.overridden_opcodes

def set_opcode_overrides(ops):
    """Set the overridden behavior of specified opcodes.

    This affects all Stack steps that run afterward.
    """
    opcodes.set_overridden_opcodes(ops)

def set_to_preset(name):
    """Reset chainparams to the preset name."""
    # Will throw an exception if name isn't a preset.
    params = presets[name]
    set_tx_fields(params.tx_fields)
    set_block_header_fields(params.block_header_fields)
    set_block_fields(params.block_fields)
    set_opcode_overrides(params.opcode_overrides)
