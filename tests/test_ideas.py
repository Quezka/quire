from datetime import date, datetime, timedelta

from quire.domain.ideas import Idea, first_line, matches, resurface, tags


def test_tags_are_words_in_the_text():
    assert tags("A shelf for the #3DS games #home #Home") == ["3ds", "home"]
    assert tags("issue #12 and a#b") == ["12"]
    assert tags("no tags") == []


def test_search_needs_every_word_and_tag():
    idea = Idea("Ask Sam about the #school trip", datetime(2026, 11, 1))
    assert matches(idea, "sam trip")
    assert matches(idea, "#school")
    assert not matches(idea, "#game")
    assert not matches(idea, "sam museum")
    assert matches(idea, "")


def test_an_old_open_idea_comes_back_now_and_then():
    today = date(2026, 11, 15)
    old = Idea("old", datetime(2026, 11, 1), id=1)
    older = Idea("older", datetime(2026, 10, 1), id=2)
    fresh = Idea("fresh", datetime(2026, 11, 14), id=3)
    done = Idea("done", datetime(2026, 9, 1), True, id=4)
    assert resurface([old, older, fresh, done], today, {}).id == 2  # oldest of the never shown
    assert resurface([old, older], today, {"2": "2026-11-10"}).id == 1  # 2 was shown 5 days ago
    assert resurface([older], today, {"2": (today - timedelta(days=3)).isoformat()}) is None


def test_a_task_title_is_the_first_line_without_tags():
    assert first_line("Buy #home paint\nwhite, 2 l") == "Buy paint"
    assert first_line("word " * 50, 20).endswith("…")


def test_an_idea_becomes_a_task_or_a_note(services, clock):
    ideas = services.ideas
    a = ideas.add("Fix the bike light #bike\nfront one")
    task_id = ideas.to_task(a, clock.now().date())
    task = services.tasks.task(task_id)
    assert task.title == "Fix the bike light" and "front one" in task.details
    assert [i.done for i in ideas.ideas() if i.id == a] == [True]
    b = ideas.add("Story about a penguin")
    ideas.to_note(b)
    assert any("Story about a penguin" in n.title for n in services.notes.search())
    assert ideas.all_tags() == []  # both done


def test_a_deleted_idea_can_be_brought_back(services):
    ideas = services.ideas
    i = ideas.add("keep me #x")
    record = [r for r in ideas.ideas() if r.id == i][0]
    ideas.delete(i)
    ideas.restore(record)
    assert [r.text for r in ideas.ideas()] == ["keep me #x"]
    assert ideas.ideas(query="#x")[0].tags == ("x",)


def test_resurfacing_is_remembered(services, clock):
    ideas = services.ideas
    ideas.add("an old thought")
    clock._today += timedelta(days=10)
    shown = ideas.resurfaced(mark=True)
    assert shown is not None and shown.text == "an old thought"
    assert ideas.resurfaced() is None  # shown today: not again for two weeks
