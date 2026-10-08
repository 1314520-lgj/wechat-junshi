"""Speaker ownership is part of verified advice, independent of random IDs."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
if not (ROOT / 'engine').is_dir():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / 'engine'))
import engine
import content
import replycache
import replycheck


def messages(first='person-a', second='person-a', confidence='visual_candidate'):
    return [
        {'from': 'her', 'text': '我很难过', 'kind': 'text', 'name': '小明',
         'speaker_id': first, 'identity_confidence': confidence, 'identity_scope': 'observation'},
        {'from': 'her', 'text': '', 'kind': 'sticker', 'name': '小明',
         'speaker_id': second, 'identity_confidence': confidence, 'identity_scope': 'observation',
         'media_description': '卡通人物低头流泪', 'media_understanding_complete': True},
    ]


class CacheSpeakerScope(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        with replycache._lock:
            self.saved = deepcopy(replycache._entries)
            replycache._entries.clear()
        self.addCleanup(self.restore_entries)

    def restore_entries(self):
        with replycache._lock:
            replycache._entries.clear()
            replycache._entries.update(self.saved)

    def key(self, rows, unresolved=False):
        return replycache.key_for(engine._analyze_impl, (rows, '朋友', 'synthetic-key'), {},
                                  self.home.name, allow_unresolved=unresolved)

    def test_changed_ownership_changes_grounding_and_cache_key(self):
        same = messages()
        different = messages(second='person-b')
        self.assertTrue(replycheck.grounded('我知道你很难过', same))
        self.assertFalse(replycheck.grounded('我知道你很难过', different))
        self.assertNotEqual(self.key(same), self.key(different))

    def test_regenerated_ids_preserve_same_and_distinct_groups(self):
        self.assertEqual(self.key(messages()), self.key(messages('new-a', 'new-a')))
        self.assertEqual(self.key(messages(second='person-b')), self.key(messages('new-a', 'new-b')))

    def test_missing_ids_do_not_reuse_identified_ownership(self):
        missing = messages(second=None)
        self.assertNotEqual(self.key(missing), self.key(messages()))
        self.assertNotEqual(self.key(missing), self.key(messages(second='person-b')))
        missing[1].pop('speaker_id')
        self.assertNotEqual(self.key(missing), self.key(messages(second=None)))

    def test_absent_id_and_explicit_missing_id_have_different_grounding(self):
        implicit = messages()
        implicit[1].pop('speaker_id')
        explicit = messages(second=None)
        self.assertFalse(replycheck.grounded('我知道你很难过', content.annotate(implicit, '')))
        self.assertTrue(replycheck.grounded('我知道你很难过', content.annotate(explicit, '')))
        self.assertNotEqual(self.key(implicit), self.key(explicit))

    def test_confirmed_link_is_preserved_when_confirmed_message_is_later(self):
        linked = messages()
        linked[1]['identity_confidence'] = 'user_confirmed'
        unlinked = deepcopy(linked)
        unlinked[0]['speaker_id'] = 'person-b'
        self.assertNotEqual(self.key(linked), self.key(unlinked))

    def test_unknown_confidence_still_preserves_relative_ownership(self):
        self.assertNotEqual(self.key(messages(confidence='unknown')),
                            self.key(messages(second='person-b', confidence='unknown')))

    def test_observation_sentinels_follow_existing_guard_semantics(self):
        first = messages('observation-a', 'observation-a', 'display_name_only')
        reread = messages('observation-x', 'observation-y', 'display_name_only')
        self.assertTrue(replycheck.same_observed_speaker(reread[0], reread[1]))
        self.assertEqual(self.key(first), self.key(reread))
        mixed = messages('observation-x', 'person-y', 'display_name_only')
        self.assertFalse(replycheck.same_observed_speaker(mixed[0], mixed[1]))
        self.assertNotEqual(self.key(first), self.key(mixed))

    def test_confirmed_absolute_links_are_preserved(self):
        self.assertNotEqual(self.key(messages(confidence='user_confirmed')),
                            self.key(messages('new-a', 'new-a', 'user_confirmed')))
        linked = messages()
        linked[0]['identity_confidence'] = 'user_confirmed'
        unlinked = deepcopy(linked)
        unlinked[1]['speaker_id'] = 'person-b'
        self.assertNotEqual(self.key(linked), self.key(unlinked))

    def test_unconfirmed_sentinel_link_to_confirmed_id_is_preserved(self):
        linked = messages('observation-a', 'observation-a', 'display_name_only')
        linked[0]['identity_confidence'] = 'user_confirmed'
        unlinked = deepcopy(linked)
        unlinked[1]['speaker_id'] = 'observation-b'
        self.assertTrue(replycheck.same_observed_speaker(linked[0], linked[1]))
        self.assertFalse(replycheck.same_observed_speaker(unlinked[0], unlinked[1]))
        self.assertNotEqual(self.key(linked), self.key(unlinked))

    def test_unresolved_flight_key_also_distinguishes_ownership(self):
        same, different = messages(), messages(second='person-b')
        for rows in (same, different):
            rows[1].pop('media_description')
            rows[1].pop('media_understanding_complete')
        self.assertIsNone(self.key(same))
        self.assertNotEqual(self.key(same, unresolved=True), self.key(different, unresolved=True))

    def test_invalid_id_disables_reuse_instead_of_collapsing_ownership(self):
        for invalid in ({'id': 'x'}, ['x'], 7, True):
            with self.subTest(invalid=invalid):
                rows = messages(second=invalid)
                self.assertIsNone(self.key(rows))

    def test_actual_cache_hit_reuses_generation_only_for_equal_ownership(self):
        def draft(rows, *args, **kwargs):
            candidate = '我知道你很难过' if replycheck.grounded('我知道你很难过', rows) else '听你说'
            return [candidate]

        def review(rows, candidates, *args, **kwargs):
            self.assertTrue(all(replycheck.grounded(candidate, rows) for candidate in candidates))
            return candidates

        settings = {'_home': self.home.name, 'vision_enabled': False}
        with patch.object(engine, 'draft_candidates', side_effect=draft) as drafts, \
             patch.object(engine, 'review', side_effect=review), \
             patch.object(engine, 'chat', side_effect=AssertionError('No model request allowed')):
            first = engine.analyze(messages(), '朋友', 'synthetic-key', settings=settings)
            reread = engine.analyze(messages('new-a', 'new-a'), '朋友', 'synthetic-key', settings=settings)
            split = engine.analyze(messages('new-a', 'new-b'), '朋友', 'synthetic-key', settings=settings)
        self.assertFalse(first['cache_hit'])
        self.assertTrue(reread['cache_hit'])
        self.assertFalse(split['cache_hit'])
        self.assertEqual(drafts.call_count, 2)
        self.assertEqual(first['best_reply'], '我知道你很难过')
        self.assertEqual(split['best_reply'], '听你说')


if __name__ == '__main__':
    unittest.main()
