import unittest
from msg_split import split_message, SplitMessageError

class TestSplitMessage(unittest.TestCase):
    def test_simple_split(self):
        # Проверим, что простое HTML без тяжёлых тегов режется корректно
        html = "<p>Hello <b>world</b></p>" * 10  # Искусственно увеличим
        max_len = 50
        fragments = list(split_message(html, max_len=max_len))
        # Проверим, что фрагментов несколько
        self.assertTrue(len(fragments) > 1)

    def test_block_closing(self):
        # Проверяем, что если max_len жёсткий, фрагменты принудительно обрываются
        # Здесь важна длина: <p>12345</p> - это 12 символов
        # <p>67890</p> - тоже 12
        # Итого должно получиться 2 фрагмента: каждый умещается ровно в 12.
        html = "<p>12345</p><p>67890</p>"
        max_len = 12
        fragments = list(split_message(html, max_len=max_len))
        # Ожидаем ровно 2 фрагмента
        self.assertEqual(len(fragments), 2, f"Фрагментов должно быть 2, а вышло: {len(fragments)}")
        # Проверяем, что каждый <= 12 символов
        for frag in fragments:
            self.assertTrue(len(frag) <= 12, f"Фрагмент '{frag}' превысил 12 символов")

    def test_big_token_exception(self):
        # Случай, когда тег настолько большой, что в пустом фрагменте не умещается
        # (или текст очень длинный, и его внутри <a> рвать нельзя)
        html = "<a>" + ("x" * 5000) + "</a>"
        with self.assertRaises(SplitMessageError):
            list(split_message(html, max_len=4096))


if __name__ == "__main__":
    unittest.main()
