IMAGE := lsstsqre/centos:7-stack-lsst_distrib-v29_2_1
WORKDIR := /home/lsst/mnt

shell:
	docker run -it --platform linux/amd64 -v "$$(pwd)":$(WORKDIR) $(IMAGE)

demo:
	docker run -it --platform linux/amd64 -v "$$(pwd)":$(WORKDIR) $(IMAGE) bash scripts/run_hsc_demo.sh

inspect:
	docker run -it --platform linux/amd64 -v "$$(pwd)":$(WORKDIR) $(IMAGE) bash -lc '\
	source /opt/lsst/software/stack/loadLSST.bash && \
	setup lsst_distrib && \
	cd $(WORKDIR)/demo/pipelines_check-29.2.1 && \
	python $(WORKDIR)/src/inspect_repo.py \
'

stats:
	docker run -it --platform linux/amd64 -v "$$(pwd)":$(WORKDIR) $(IMAGE) bash -lc '\
	source /opt/lsst/software/stack/loadLSST.bash && \
	setup lsst_distrib && \
	cd $(WORKDIR)/demo/pipelines_check-29.2.1 && \
	python $(WORKDIR)/src/read_image_stats.py \
'

run-task:
	docker run -it --platform linux/amd64 -v "$$(pwd)":$(WORKDIR) $(IMAGE) bash scripts/run_simple_calibration.sh

validate:
	docker run -it --platform linux/amd64 -v "$$(pwd)":$(WORKDIR) $(IMAGE) bash -lc '\
	source /opt/lsst/software/stack/loadLSST.bash && \
	setup lsst_distrib && \
	cd $(WORKDIR)/demo/pipelines_check-29.2.1 && \
	python $(WORKDIR)/src/validate_custom_output.py \
'
