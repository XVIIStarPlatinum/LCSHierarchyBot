"""
Тесты чистых функций-экранов (handlers/screens.py).
"""

from unittest.mock import MagicMock

from telegram import InlineKeyboardMarkup

from handlers.screens import (
    render_entrance_hall,
    render_profile_screen,
    render_top_screen,
)


class TestRenderEntranceHall:
    def test_regular_user_has_no_owner_or_admin_text(self):
        text, keyboard = render_entrance_hall(is_owner=False, is_admin=False)

        assert "создатель сообщества" not in text
        assert "Привет, админ!" not in text
        assert "Добро пожаловать в сообщество!" in text
        assert isinstance(keyboard, InlineKeyboardMarkup)

    def test_owner_gets_owner_specific_text(self):
        text, _ = render_entrance_hall(is_owner=True, is_admin=False)

        assert "создатель сообщества" in text
        assert "/legend" in text
        assert "/setadmin" in text

    def test_admin_gets_admin_specific_text_not_owner_text(self):
        text, _ = render_entrance_hall(is_owner=False, is_admin=True)

        assert "Привет, админ!" in text
        assert "создатель сообщества" not in text
        # Владельческие команды не должны утекать в текст для админа
        assert "/legend" not in text

    def test_owner_takes_precedence_over_admin(self):
        # На практике владелец всегда одновременно и админ — здесь
        # проверяем, что при обоих флагах выигрывает владельческий текст.
        text, _ = render_entrance_hall(is_owner=True, is_admin=True)
        assert "создатель сообщества" in text

    def test_keyboard_has_working_profile_and_top_buttons(self):
        _, keyboard = render_entrance_hall(is_owner=False, is_admin=False)

        buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        assert len(buttons) == 2
        callback_data_values = [btn.callback_data for btn in buttons]
        assert "nav:profile" in callback_data_values
        assert "nav:top" in callback_data_values

    def test_no_dead_view_profile_or_view_top_buttons(self):
        # Регрессия: раньше здесь были view_profile/view_top без
        # зарегистрированного обработчика — они не должны вернуться.
        _, keyboard = render_entrance_hall(is_owner=True, is_admin=True)
        callback_data_values = [
            btn.callback_data
            for row in keyboard.inline_keyboard
            for btn in row
            if btn.callback_data
        ]
        assert "view_profile" not in callback_data_values
        assert "view_top" not in callback_data_values


class TestRenderProfileScreen:
    def _make_profile(self, **overrides):
        profile = {
            "user_id": 123,
            "username": "testuser",
            "rank": "Активист",
            "points": 250.5,
            "position": 4,
        }
        profile.update(overrides)
        return profile

    def _make_rank_system(self, privileges=None):
        # get_user_restrictions is intentionally NOT mocked here — it's a
        # pure module-level function (not a RankSystem method), and
        # calling the real thing directly guards against the exact
        # AttributeError/stale-text bugs this was shipping with.
        rank_system = MagicMock()
        rank_system.get_user_privileges.return_value = privileges or []
        return rank_system

    def test_basic_fields_present(self):
        profile = self._make_profile()
        rank_system = self._make_rank_system()

        text, _ = render_profile_screen(profile, rank_system)

        assert "@testuser" in text
        assert "250.5" in text
        assert "Место:</b> 4" in text

    def test_username_falls_back_to_user_id_when_missing(self):
        profile = self._make_profile(username=None)
        rank_system = self._make_rank_system()

        text, _ = render_profile_screen(profile, rank_system)

        assert "@user123" in text

    def test_privileges_listed_when_present(self):
        profile = self._make_profile()
        rank_system = self._make_rank_system(
            privileges=["Голосовые сообщения", "Отправка фотографий"],
        )

        text, _ = render_profile_screen(profile, rank_system)

        assert "1. Голосовые сообщения" in text
        assert "2. Отправка фотографий" in text

    def test_empty_privileges_show_placeholder_text(self):
        profile = self._make_profile()
        rank_system = self._make_rank_system(privileges=[])

        text, _ = render_profile_screen(profile, rank_system)

        assert "Нет особых привилегий" in text

    def test_real_restrictions_render_for_novice_and_reflect_current_decay(self):
        # Regression guard: this is the exact call that used to crash with
        # AttributeError (get_user_restrictions was called as a RankSystem
        # method, but it's a module-level function), and the text it
        # returned used to describe the old hourly-decay mechanic.
        profile = self._make_profile(rank="Новичок")
        rank_system = self._make_rank_system()

        text, _ = render_profile_screen(profile, rank_system)

        assert "1. Нельзя скачивать файлы" in text
        assert "24 часа без сообщений и реакций" in text
        assert "каждый час" not in text  # old, now-incorrect decay wording

    def test_real_restrictions_for_trainee_no_longer_mention_decay(self):
        # Стажёр no longer decays at all (client's final call) — the old
        # text incorrectly said "-0.1 балла каждый час" for this rank.
        profile = self._make_profile(rank="Стажёр")
        rank_system = self._make_rank_system()

        text, _ = render_profile_screen(profile, rank_system)

        assert "Удаление ботом за 3 дня бездействия" in text
        assert "каждый час" not in text

    def test_high_rank_has_no_restrictions_placeholder(self):
        profile = self._make_profile(rank="Легенда")
        rank_system = self._make_rank_system()

        text, _ = render_profile_screen(profile, rank_system)

        assert "Нет ограничений" in text

    def test_keyboard_has_home_button(self):
        profile = self._make_profile()
        rank_system = self._make_rank_system()

        _, keyboard = render_profile_screen(profile, rank_system)

        buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        assert len(buttons) == 1
        assert buttons[0].callback_data == "nav:home"


class TestRenderTopScreen:
    def test_empty_list_shows_placeholder_text(self):
        text, _ = render_top_screen([])

        assert "пока пуст" in text

    def test_empty_list_still_has_home_button(self):
        _, keyboard = render_top_screen([])

        buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        assert len(buttons) == 1
        assert buttons[0].callback_data == "nav:home"

    def test_users_listed_in_order_with_points(self):
        top_users = [
            {"user_id": 1, "username": "alice", "points": 500.0},
            {"user_id": 2, "username": "bob", "points": 300.5},
        ]

        text, _ = render_top_screen(top_users)

        assert "1. @alice - 500.0 баллов" in text
        assert "2. @bob - 300.5 баллов" in text

    def test_top_three_get_medals(self):
        top_users = [
            {"user_id": 1, "username": "first", "points": 100.0},
            {"user_id": 2, "username": "second", "points": 90.0},
            {"user_id": 3, "username": "third", "points": 80.0},
            {"user_id": 4, "username": "fourth", "points": 70.0},
        ]

        text, _ = render_top_screen(top_users)

        assert "🥇1. @first" in text
        assert "🥈2. @second" in text
        assert "🥉3. @third" in text
        assert "4. @fourth" in text
        assert "🥇4." not in text

    def test_username_falls_back_to_user_id_when_missing(self):
        top_users = [{"user_id": 42, "username": None, "points": 10.0}]

        text, _ = render_top_screen(top_users)

        assert "@user42" in text

    def test_keyboard_has_home_button(self):
        top_users = [{"user_id": 1, "username": "alice", "points": 1.0}]

        _, keyboard = render_top_screen(top_users)

        buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        assert len(buttons) == 1
        assert buttons[0].callback_data == "nav:home"
