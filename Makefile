.PHONY: structs test

# make structs PRODUCT=epdc
structs:
	python -m engine.struct_gen $(PRODUCT)

.PHONY: test
test:
	python -m pytest
