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
    # The three harvest families are base + per_item, not flat per-kami
    # constants — see HARVEST below and TestHarvestCeilings.
}

# kami-oracle, measured 2026-08-27 over receipt-status=1 transactions
# since 2026-06-01, joining raw_tx to kami_action on tx_hash and counting
# DISTINCT kami_id per tx to recover the batch size.
# key -> {batch size: (p95, tx count)}
HARVEST = {
    "harvest_start": {1: (1_636_037, 349_296), 12: (9_339_266, 857),
                      25: (18_385_855, 67)},
    "harvest_stop": {1: (2_645_724, 366_809), 12: (19_029_290, 1_321)},
    "harvest_collect": {1: (2_465_867, 37_805), 12: (16_844_165, 35)},
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
        "harvest_start_base", "harvest_start_per_item",
        "harvest_stop_base", "harvest_stop_per_item",
        "harvest_collect_base", "harvest_collect_per_item",
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

    def test_max_tx_gas_is_the_lane_cap(self):
        """The chain refuses a gas limit over its per-transaction lane
        cap, so a ceiling above it can never reject what the lane does.
        Observed live 2026-08-27: `tx gas limit 40000000 exceeds max lane
        gas limit 31500000`."""
        assert server.MAX_TX_GAS == 31_500_000


class TestHarvestCeilings:
    """base + per_item, pinned against the oracle measurement.

    A FLAT per-kami constant cannot serve this cost curve. Harvest gas is
    base + slope x n with a large fixed term, so a constant big enough
    for one kami over-provisions every batch (13 kamis fitted in no
    transaction, while three docstrings promised one), and a constant
    small enough to batch under-provisions the single-kami call — which
    is the most common call in the table by two orders of magnitude.
    """

    @pytest.mark.parametrize("key", sorted(HARVEST))
    def test_clears_p95_at_every_measured_batch_size(self, key):
        for n, (p95, txs) in sorted(HARVEST[key].items()):
            gas = server._harvest_gas(key, n)
            assert gas >= p95, (
                f"{key} at n={n} provisions {gas:,}, under the measured "
                f"p95 {p95:,} ({txs:,} tx)"
            )

    @pytest.mark.parametrize("key", sorted(HARVEST))
    def test_single_kami_call_is_provisioned(self, key):
        """The regression the flat-constant proposal would have shipped:
        1,100,000 for harvest_start is 33% UNDER its single-kami p95."""
        p95, txs = HARVEST[key][1]
        assert server._harvest_gas(key, 1) > p95, (
            f"{key} provisions {server._harvest_gas(key, 1):,} for one "
            f"kami, under the {p95:,} p95 of {txs:,} observed calls"
        )

    @pytest.mark.parametrize("key", sorted(HARVEST))
    def test_thirteen_kamis_fit_in_one_transaction(self, key):
        """A 13-kami team is one start tx and one stop tx, which is what
        the docstrings say. Under the old flat constants it was two of
        each."""
        assert server._harvest_gas(key, 13) <= server.MAX_TX_GAS

    def test_margin_stays_reasonable(self):
        """Provisioning is ~1.3x p95, not 4x: an over-provisioned batch
        is refused by the lane long before it is refused by the block."""
        for key, points in HARVEST.items():
            for n, (p95, _) in points.items():
                ratio = server._harvest_gas(key, n) / p95
                assert 1.15 <= ratio <= 1.6, (
                    f"{key} at n={n} provisions {ratio:.2f}x p95"
                )

    def test_docstring_caps_match_the_arithmetic(self):
        """Each batch docstring states a per-call maximum; it must be the
        number the lane cap and the constants actually produce."""
        tools = {t.name: t for t in server.mcp._tool_manager.list_tools()}
        for key, tool in (
            ("harvest_start", "harvest_start"),
            ("harvest_stop", "harvest_stop"),
            ("harvest_collect", "harvest_collect"),
        ):
            fits = server._harvest_max_per_call(key)
            assert f"(at most {fits})" in (tools[tool].description or ""), (
                f"{tool} does not state its real per-call maximum {fits}"
            )
            assert server._harvest_gas(key, fits) <= server.MAX_TX_GAS
            with pytest.raises(server.PreTxValidationError):
                server._harvest_gas(key, fits + 1)
