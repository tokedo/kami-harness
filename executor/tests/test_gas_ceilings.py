"""Gas-ceiling floors, pinned against observed on-chain usage.

Why this file exists. A gas ceiling set below what a call really costs
does not fail loudly or degrade gracefully: the transaction is accepted,
lands, burns the entire ceiling, and reverts out-of-gas with empty revert
data. Nothing upstream catches it — the pre-send eth_call dry-run runs
WITHOUT a ceiling, so it passes every time while the real transaction
dies. `system.harvest.collect` was provisioned at 2,000,000 against a
median successful cost of 2,359,919 and failed 12 times out of 12
on-chain, each one recorded as an unexplained empty revert.

So each ceiling is pinned here against a floor derived from gas actually
consumed by SUCCESSFUL transactions of the same system, measured over
2026-05-01..2026-08-07. The floors are deliberately below the ceilings:
this asserts that a ceiling still clears observed usage, not that it
equals today's chosen value, so ordinary tuning stays free while a silent
lowering back under real usage fails.
"""

import pytest

import server

# tool key -> (floor, single-call p50, note). The floor is ~1.5x the
# single-call p99, or the observed maximum where the p99 is inflated by
# batched calls.
OBSERVED = {
    "register_account": (1_325_000, 883_040, "p99 883,112 / max 892,864"),
    "move_to_room": (1_625_000, 860_277, "p99 1,083,261 / max 1,085,203"),
    "travel_use_item": (3_305_000, 1_389_965, "p99 2,203,269 / max 2,639,799"),
    "auction_buy": (1_535_000, 941_910, "p99 1,023,644 / max 1,038,431"),
    "equip_kami": (2_213_000, 1_139_006, "p99 1,475,614 / max 1,587,696"),
    "unequip_kami": (1_546_000, 903_198, "p99 1,030,941 / max 1,030,941"),
    "cancel_kami_listing": (1_410_000, 728_851, "p99 940,015 / max 950,688"),
    "accept_quest": (1_436_000, 837_098, "p99 957,476 / max 1,117,822"),
    "complete_quest": (1_751_000, 943_620, "p99 1,167,339 / max 1,594,420"),
    "drop_quest": (931_000, 613_887, "p99 621,069 / max 621,069 (n=14)"),
    "craft_item": (2_112_000, 1_159_834, "p99 1,408,180 / max 1,701,712"),
    "scavenge_claim": (1_168_000, 779_040, "p99 779,082 / max 783,982"),
    "sacrifice_kami": (1_965_000, 1_240_248, "p99 1,310,222 / max 1,345,462"),
    "liquidate_kami": (7_125_000, 4_343_014, "p99 4,750,112 / max 5,386,977"),
    "skill_respec": (7_722_000, 4_347_883, "p99 5,148,177 / max 5,407,222"),
    "cast_item": (3_773_000, 2_323_182, "p99 2,515,613 / max 2,578,486"),
    "newbie_vendor_buy": (7_806_000, 2_360_307, "p99 5,204,448 (n=6)"),
    "pool_swap": (1_281_000, 714_821, "p99 854,317 / max 881,129"),
    # Per-kami ceilings: the batch path multiplies these by batch size,
    # so the floor is the single-kami requirement.
    "harvest_start": (2_416_000, 1_611_201, "p50 x1.5; p99/max batch-inflated"),
    "harvest_stop": (3_896_000, 2_597_439, "p50 x1.5; p99/max batch-inflated"),
    "harvest_collect": (3_539_000, 2_359_919, "p99 2,479,603 single-collect"),
}


@pytest.mark.parametrize("key", sorted(OBSERVED))
def test_ceiling_clears_observed_usage(key):
    floor, p50, note = OBSERVED[key]
    ceiling = server._GAS_CEILINGS[key]
    assert ceiling >= floor, (
        f"{key} ceiling {ceiling:,} is below its justified floor "
        f"{floor:,} ({note}). A ceiling under real usage does not fail "
        f"gracefully: the tx lands, burns the whole ceiling, and reverts "
        f"out-of-gas with empty revert data."
    )


@pytest.mark.parametrize("key", sorted(OBSERVED))
def test_ceiling_never_below_median_success(key):
    """The floor above is the real bar; this states the weaker one that
    the harvest_collect class violated, so a regression that far is
    unmistakable in the failure output."""
    _, p50, note = OBSERVED[key]
    ceiling = server._GAS_CEILINGS[key]
    assert ceiling > p50, (
        f"{key} ceiling {ceiling:,} is below the MEDIAN cost of a "
        f"successful call ({p50:,}) — this tool cannot succeed on-chain"
    )


def test_every_ceiling_is_justified():
    """No ceiling may be added without an observed-usage floor here."""
    scaling_terms = {
        "listing_buy_base", "listing_buy_per_item",
        "buy_kami_base", "buy_kami_per_item",
        "transfer_kami_base", "transfer_kami_per_item",
        "transfer_items_base", "transfer_items_per_item",
        "burn_items_base", "burn_items_per_item",
        "gacha_use_base", "gacha_use_per_item",
        # system.chat has no observed successful transactions (chat is
        # disabled in deployments), so it has no floor to pin.
        "chat_send",
    }
    unjustified = set(server._GAS_CEILINGS) - set(OBSERVED) - scaling_terms
    assert not unjustified, (
        f"gas ceilings with no observed-usage floor: {sorted(unjustified)}"
    )


class TestScalingCeilings:
    """Base + per-item formulas, checked on BOTH terms."""

    def test_single_item_clears_median(self):
        cases = [
            ("listing_buy", 949_468),
            ("buy_kami", 1_072_524),
            ("transfer_kami", 782_915),
            ("transfer_items", 651_652),
        ]
        for name, p50 in cases:
            one = (server._GAS_CEILINGS[f"{name}_base"]
                   + server._GAS_CEILINGS[f"{name}_per_item"])
            assert one > p50, (
                f"{name} at one item provisions {one:,}, under the "
                f"{p50:,} median successful cost"
            )

    def test_batch_term_covers_observed_maximum(self):
        # (name, observed max, batch size that maximum represents)
        cases = [
            ("listing_buy", 3_114_738, 3),
            ("buy_kami", 12_434_456, 9),
            ("transfer_kami", 3_899_601, 4),
            ("transfer_items", 2_660_695, 8),
        ]
        for name, observed_max, size in cases:
            gas = (server._GAS_CEILINGS[f"{name}_base"]
                   + server._GAS_CEILINGS[f"{name}_per_item"] * size)
            assert gas >= observed_max, (
                f"{name} at {size} items provisions {gas:,}, under the "
                f"{observed_max:,} observed maximum"
            )

    def test_gacha_clears_its_median(self):
        """The mint cost is dominated by a large fixed term: the observed
        maximum is only ~1.2x the median across all mint counts."""
        one = (server._GAS_CEILINGS["gacha_use_base"]
               + server._GAS_CEILINGS["gacha_use_per_item"])
        assert one > 10_646_224, (
            f"a single gacha mint provisions {one:,}, under the "
            f"10,646,224 median successful cost"
        )
        assert one >= 12_786_799, "must clear the observed maximum too"


class TestBlockLimitGuard:
    """No formula may provision a transaction a block cannot hold."""

    def test_max_tx_gas_under_block_limit(self):
        # Block gas limit observed at 45,000,000 (block 31,808,156).
        assert server.MAX_TX_GAS < 45_000_000

    def test_oversized_batch_rejected_before_signing(self):
        with pytest.raises(server.PreTxValidationError) as ei:
            server._batch_gas(1_000_000, 4_000_000, 500, "kamis")
        msg = str(ei.value)
        assert "Split into calls of at most" in msg
        assert "45,000,000" in msg  # the real constraint is named

    def test_guard_states_a_size_that_actually_fits(self):
        with pytest.raises(server.PreTxValidationError) as ei:
            server._batch_gas(1_000_000, 4_000_000, 500, "kamis")
        suggested = int(str(ei.value).split("at most ")[1].split()[0])
        assert 1_000_000 + 4_000_000 * suggested <= server.MAX_TX_GAS

    def test_ordinary_batch_passes_through(self):
        assert server._batch_gas(1_000_000, 4_000_000, 3, "kamis") == 13_000_000

    def test_harvest_batch_ceiling_scales_with_size(self):
        """The per-kami ceiling multiplied by the batch — the defect was a
        single-kami allowance covering a whole roster."""
        per_kami = server._GAS_CEILINGS["harvest_collect"]
        assert server._batch_gas(0, per_kami, 5, "kamis") == per_kami * 5
