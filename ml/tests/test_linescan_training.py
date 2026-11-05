import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from linescan_training import history_trainer


def test_epoch_history_is_saved_when_inline_evaluation_is_disabled():
    class Trainer:
        rank = 0

        def __init__(self):
            self.saved = []

        def after_epoch(self):
            self.save_ckpt("latest")

        def save_ckpt(self, name):
            self.saved.append(name)

    trainer = history_trainer(Trainer)()
    for epoch in range(8):
        trainer.epoch = epoch
        trainer.after_epoch()
    assert [name for name in trainer.saved if name != "latest"] == [
        "epoch_2",
        "epoch_4",
        "epoch_6",
        "epoch_8",
    ]
