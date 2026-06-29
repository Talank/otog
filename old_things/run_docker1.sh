module_ids_we_are_considering=(24)

for i in {1..40}
do
    if [[ ! " ${module_ids_we_are_considering[@]} " =~ " $i " ]]; then
        continue
    fi

    docker build -t dockerized-otog /home/tbaral/research/otog_icse/docker_project_template
    docker run --name otog-container2_$i --memory=8g --memory-swap=8g -e ID=$i dockerized-otog

    # mkdir -p /home/tbaral/research/otog_icse/results/$i

    # docker start otog-container2_$i

    docker cp otog-container2_$i:/app/scripts/dataset /home/tbaral/research/otog_icse/results/$i/
    docker cp otog-container2_$i:/app/scripts/test_list /home/tbaral/research/otog_icse/results/$i/
    docker cp otog-container2_$i:/app/scripts/runs_n25 /home/tbaral/research/otog_icse/results/$i/
    docker cp otog-container2_$i:/app/scripts/random_test_orders_n25 /home/tbaral/research/otog_icse/results/$i/

    # docker stop otog-container2_$i
    # docker rm otog-container2_$i
done