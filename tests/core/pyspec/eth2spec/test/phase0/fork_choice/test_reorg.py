from eth2spec.test.context import (
    spec_state_test,
    with_all_phases,
    with_presets,
)
from eth2spec.test.helpers.constants import (
    MINIMAL,
)
from eth2spec.test.helpers.attestations import (
    state_transition_with_full_block,
)
from eth2spec.test.helpers.block import (
    build_empty_block,
)
from eth2spec.test.helpers.fork_choice import (
    get_genesis_forkchoice_store_and_block,
    on_tick_and_append_step,
    tick_and_add_block,
    apply_next_epoch_with_attestations,
    find_next_justifying_slot,
)
from eth2spec.test.helpers.state import (
    state_transition_and_sign_block,
    next_epoch,
    transition_to,
)


@with_all_phases
@spec_state_test
@with_presets([MINIMAL], reason="too slow")
def test_easy_reorg(spec, state):
    """
    {      epoch 4     }{     epoch 5     }
    [c4]<--[x]<--[y]<-------[empty_y']
             ↑______________[z]

    At c4, c3 is the latest justifized checkpoint (or something earlier)
    The block x can justifize c4.
    empty_y': skipped slot at the first slot of epoch 5.
    z: the child of block of x at the first slot of epoch 5.

    block z can reorg the chain from block y easily!
    """
    test_steps = []
    # Initialization
    store, anchor_block = get_genesis_forkchoice_store_and_block(spec, state)
    yield 'anchor_state', state
    yield 'anchor_block', anchor_block
    current_time = state.slot * spec.config.SECONDS_PER_SLOT + store.genesis_time
    on_tick_and_append_step(spec, store, current_time, test_steps)
    assert store.time == current_time

    next_epoch(spec, state)
    on_tick_and_append_step(spec, store, store.genesis_time + state.slot * spec.config.SECONDS_PER_SLOT, test_steps)

    # Fill epoch 1 to 3
    for _ in range(3):
        state, store, _ = yield from apply_next_epoch_with_attestations(
            spec, state, store, True, True, test_steps=test_steps)

    assert state.current_justified_checkpoint.epoch == store.justified_checkpoint.epoch == 3

    # Try to find the block that can justify epoch 4
    signed_blocks, justified_slot = find_next_justifying_slot(
        spec, state, True, True)

    for signed_block in signed_blocks:
        yield from tick_and_add_block(spec, store, signed_block, test_steps)
        spec.get_head(store) == signed_block.message.hash_tree_root()
    state = store.block_states[spec.get_head(store)].copy()
    assert state.current_justified_checkpoint.epoch == 3
    state_x = state.copy()

    signed_block_y = state_transition_with_full_block(spec, state, True, True)

    yield from tick_and_add_block(spec, store, signed_block_y, test_steps)
    assert spec.get_head(store) == signed_block_y.message.hash_tree_root()
    assert store.justified_checkpoint.epoch == 3
    state = state_x.copy()

    # transition to the last slot of epoch 4
    transition_to(spec, state, state.slot + ((state.slot + spec.SLOTS_PER_EPOCH) % spec.SLOTS_PER_EPOCH) - 1)

    block_z = build_empty_block(spec, state, slot=state.slot + 1)
    signed_block_z = state_transition_and_sign_block(spec, state, block_z)
    yield from tick_and_add_block(spec, store, signed_block_z, test_steps)
    assert spec.get_head(store) == signed_block_z.message.hash_tree_root()
    assert state.current_justified_checkpoint.epoch == store.justified_checkpoint.epoch == 4
