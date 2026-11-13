starter:
	py -m src.gen.run --scale starter --seed 20261022 --out out/starter

clean:
	py -m src.gen.run --scale starter --seed 20261022 --out out/clean --clean
	py -m src.validate.checks out/clean

full:
	py -m src.gen.run --scale full --seed 20261022 --out out/full

validate:
	py -m src.validate.checks out/starter

repro:
	py -m src.gen.run --scale full --seed 20261022 --out out/repro_a --clean
	py -m src.gen.run --scale full --seed 20261022 --out out/repro_b --clean
	py -m src.gen.run --scale starter --seed 20261023 --out out/repro_different_seed --clean
	py -m src.eval.repro out/repro_a out/repro_b out/repro_different_seed out/reproducibility_report.md

test:
	py -m pytest -q
